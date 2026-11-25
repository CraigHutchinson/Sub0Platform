#include <algorithm>
#include <array>
#include <atomic>
#include <cerrno>
#include <charconv>
#include <cmath>
#include <format>
#include <string_view>
#include <thread>

#include "sub0platform/dirs.hpp"
#include "sub0platform/file.hpp"
#include "sub0platform/lease.hpp"
#include "sub0platform/proc.hpp"

namespace sub0platform {

namespace {

namespace fs = std::filesystem;
using Clock = std::chrono::steady_clock;
constexpr double kTimeLimit = 32535216000.0;

fs::path sidecar(fs::path path, std::string_view suffix)
{
    path += suffix;
    return path;
}

std::string_view modeName(LeaseMode mode)
{
    return mode == LeaseMode::shared ? "shared" : "exclusive";
}

std::string quote(std::string_view s)
{
    std::string out = "\"";
    for (unsigned char c : s) {
        if (c == '"' || c == '\\') out += '\\';
        if (c < 0x20) out += std::format("\\u{:04x}", c);
        else out += static_cast<char>(c);
    }
    out += '"';
    return out;
}

using TextFields = std::array<std::pair<std::string_view, std::string*>, 6>;

TextFields fields(LeaseOwner& owner)
{
    return {{{"what", &owner.what}, {"tool", &owner.tool},
             {"cores", &owner.resources.cores}, {"memory_bandwidth", &owner.resources.memoryBandwidth},
             {"gpu", &owner.resources.gpu}, {"power_state", &owner.resources.powerState}}};
}

std::string encode(LeaseOwner& owner)
{
    auto json = std::format(R"({{"pid":{},"time":{:.6f},"mode":"{}")", owner.pid, owner.time, modeName(owner.mode));
    for (const auto& [key, value] : fields(owner)) {
        json += std::format(",\"{}\":{}", key, quote(*value));
    }
    return json + "}\n";
}

// The owner record is a flat object of strings and numbers. Read JSON escapes so the Python writer and legacy records interoperate.
class RecordReader
{
public:
    explicit RecordReader(std::string_view text) : text_(text) {}

    bool consume(char expected)
    {
        space();
        if (text_.empty() || text_.front() != expected) return false;
        text_.remove_prefix(1);
        return true;
    }

    bool finished()
    {
        space();
        return text_.empty();
    }

    std::optional<std::string> string()
    {
        if (!consume('"')) return std::nullopt;
        std::string out;
        while (!text_.empty()) {
            const auto c = pop();
            if (c == '"') return out;
            if (static_cast<unsigned char>(c) < 0x20) return std::nullopt;
            if (c != '\\') {
                out += c;
                continue;
            }
            if (text_.empty()) return std::nullopt;
            const char escaped = pop();
            constexpr std::string_view escapes = "\"\\/bfnrt";
            constexpr std::string_view decoded = "\"\\/\b\f\n\r\t";
            const auto index = escapes.find(escaped);
            if (index != std::string_view::npos) out += decoded[index];
            else if (escaped != 'u' || !unicode(out)) return std::nullopt;
        }
        return std::nullopt;
    }

    template<class T>
    bool number(T& value)
    {
        space();
        if (text_.empty()) return false;
        const auto [end, error] = std::from_chars(text_.data(), text_.data() + text_.size(), value);
        if (error != std::errc{}) return false;
        text_.remove_prefix(static_cast<std::size_t>(end - text_.data()));
        return true;
    }

    bool scalar()
    {
        space();
        if (text_.empty()) return false;
        if (text_.front() == '"') return string().has_value();
        for (std::string_view word : {"true", "false", "null"}) {
            if (text_.starts_with(word)) {
                text_.remove_prefix(word.size());
                return true;
            }
        }
        double unused = 0;
        return number(unused);
    }

private:
    void space()
    {
        const auto first = text_.find_first_not_of(" \r\n\t");
        text_.remove_prefix(first == std::string_view::npos ? text_.size() : first);
    }

    char pop()
    {
        const auto c = text_.front();
        text_.remove_prefix(1);
        return c;
    }

    bool hex(unsigned& value)
    {
        if (text_.size() < 4) return false;
        const auto [end, error] = std::from_chars(text_.data(), text_.data() + 4, value, 16);
        if (error != std::errc{} || end != text_.data() + 4) return false;
        text_.remove_prefix(4);
        return true;
    }

    bool unicode(std::string& out)
    {
        unsigned code = 0;
        if (!hex(code)) return false;
        if (code >= 0xd800 && code <= 0xdbff) {
            if (!text_.starts_with("\\u")) return false;
            text_.remove_prefix(2);
            unsigned low = 0;
            if (!hex(low) || low < 0xdc00 || low > 0xdfff) return false;
            code = 0x10000 + (code - 0xd800) * 0x400 + (low - 0xdc00);
        } else if (code >= 0xdc00 && code <= 0xdfff) {
            return false;
        }
        const auto continuation = [&](unsigned shift) { out += static_cast<char>(0x80 | ((code >> shift) & 0x3f)); };
        if (code < 0x80) out += static_cast<char>(code);
        else if (code < 0x800) {
            out += static_cast<char>(0xc0 | (code >> 6));
            continuation(0);
        } else if (code < 0x10000) {
            out += static_cast<char>(0xe0 | (code >> 12));
            continuation(6);
            continuation(0);
        } else {
            out += static_cast<char>(0xf0 | (code >> 18));
            continuation(12);
            continuation(6);
            continuation(0);
        }
        return true;
    }

    std::string_view text_;
};

std::optional<LeaseOwner> decode(std::string_view json)
{
    RecordReader reader(json);
    LeaseOwner owner;
    const auto text = fields(owner);
    bool hasPid = false;
    bool hasTime = false;
    if (!reader.consume('{')) return std::nullopt;
    do {
        const auto key = reader.string();
        if (!key || !reader.consume(':')) return std::nullopt;
        if (*key == "pid") {
            hasPid = reader.number(owner.pid);
            if (!hasPid) return std::nullopt;
        } else if (*key == "time") {
            hasTime = reader.number(owner.time);
            if (!hasTime) return std::nullopt;
        } else if (*key == "mode") {
            const auto value = reader.string();
            if (value == "shared") owner.mode = LeaseMode::shared;
            else if (value == "exclusive") owner.mode = LeaseMode::exclusive;
            else return std::nullopt;
        } else {
            const auto found = std::ranges::find_if(text, [&](const auto& field) { return field.first == *key; });
            if (found == text.end()) {
                if (!reader.scalar()) return std::nullopt;
                continue;
            }
            auto value = reader.string();
            if (!value) return std::nullopt;
            *found->second = std::move(*value);
        }
    } while (reader.consume(','));
    if (!reader.consume('}') || !reader.finished() || !hasPid || !hasTime || owner.pid <= 0 || owner.pid > INT32_MAX ||
        !std::isfinite(owner.time) || owner.time < 0 || owner.time >= kTimeLimit) return std::nullopt;
    return owner;
}

std::optional<LeaseOwner> liveRecord(const fs::path& path)
{
    const auto contents = readFile(path);
    if (!contents) return std::nullopt;
    auto owner = decode(*contents);
    if (!owner) return std::nullopt;
    const auto start = processStart(owner->pid);
    if (!start || !isAlive(owner->pid, *start)) return std::nullopt;
    return owner;
}

PlatformError pathError(std::string operation, std::error_code error)
{
    return PlatformError{std::move(operation), error.value(), error.message()};
}

std::expected<void, PlatformError> makeDirectory(const fs::path& path)
{
    if (path.empty()) return {};
    std::error_code error;
    fs::create_directories(path, error);
    if (error) return std::unexpected(pathError("create " + path.string(), error));
    return {};
}

std::expected<std::optional<FileLock>, PlatformError> attempt(const fs::path& path, LeaseMode mode)
{
    return mode == LeaseMode::exclusive ? FileLock::tryExclusive(path) : FileLock::tryShared(path);
}

double epochNow()
{
    return std::chrono::duration<double>(std::chrono::system_clock::now().time_since_epoch()).count();
}

std::string oneLine(std::string value)
{
    for (char& c : value) {
        if (static_cast<unsigned char>(c) < 0x20) c = ' ';
    }
    return value;
}

}  // namespace

struct MachineLease::Held
{
    FileLock lock;
    fs::path record;

    ~Held()
    {
        if (!record.empty()) {
            std::error_code error;
            fs::remove(record, error);
        }
    }
};

MachineLease::MachineLease(std::unique_ptr<Held> held) noexcept : held_{std::move(held)} {}
MachineLease::MachineLease(MachineLease&&) noexcept = default;
MachineLease& MachineLease::operator=(MachineLease&&) noexcept = default;
MachineLease::~MachineLease() = default;

std::expected<fs::path, PlatformError> MachineLease::defaultLockFile()
{
    auto directory = stateDirectory("sub0");
    if (!directory) return std::unexpected(directory.error());
    return *directory / "machine.lock";
}

std::vector<LeaseOwner> MachineLease::readOwners(const fs::path& lockFile)
{
    std::vector<LeaseOwner> owners;
    if (auto owner = liveRecord(sidecar(lockFile, ".owner"))) owners.push_back(std::move(*owner));
    const auto directory = sidecar(lockFile, ".owners");
    std::vector<fs::path> shared;
    std::error_code error;
    for (fs::directory_iterator it(directory, error), end; !error && it != end; it.increment(error)) {
        if (it->path().extension() == ".json") shared.push_back(it->path());
    }
    std::ranges::sort(shared);
    for (const auto& path : shared) {
        if (auto owner = liveRecord(path)) owners.push_back(std::move(*owner));
    }
    if (owners.empty()) {
        if (auto writer = liveRecord(sidecar(lockFile, ".writer.owner"))) owners.push_back(std::move(*writer));
    }
    return owners;
}

std::expected<std::optional<MachineLease>, PlatformError> MachineLease::acquire(
    LeaseMode mode, std::string tool, std::string what, const fs::path& lockFile, const LeaseWait& wait, LeaseResources resources)
{
    using namespace std::chrono_literals;
    const auto path = lockFile.empty() ? defaultLockFile() : std::expected<fs::path, PlatformError>{lockFile};
    if (!path) return std::unexpected(path.error());
    if (wait.timeout < 0ms) return std::unexpected(PlatformError{"take a machine lease", EINVAL, "negative lease wait"});
    if (auto made = makeDirectory(path->parent_path()); !made) return std::unexpected(made.error());

    const auto writerFile = sidecar(*path, ".writer");
    const auto maxWait = std::chrono::duration_cast<std::chrono::milliseconds>(Clock::time_point::max() - Clock::now());
    const auto deadline = Clock::now() + std::min(wait.timeout, maxWait / 2);
    LeaseOwner owner{currentProcess(), epochNow(), std::move(what), std::move(tool), mode, std::move(resources)};
    Held intent;
    for (;;) {
        if (!intent.lock.isHeld()) {
            auto attempted = attempt(writerFile, mode);
            if (!attempted) return std::unexpected(attempted.error());
            if (*attempted) intent.lock = std::move(**attempted);
        }
        if (intent.lock.isHeld()) {
            auto target = attempt(*path, mode);
            if (!target) return std::unexpected(target.error());
            if (*target) {
                auto held = std::make_unique<Held>();
                held->lock = std::move(**target);
                auto record = sidecar(*path, ".owner");
                if (mode == LeaseMode::shared) {
                    const auto directory = sidecar(*path, ".owners");
                    if (auto made = makeDirectory(directory); !made) return std::unexpected(made.error());
                    static std::atomic<std::uint64_t> serial{0};  // Uniqueness for distinct leases taken by one PID.
                    record = directory / std::format("{}-{}-{}.json", owner.pid, Clock::now().time_since_epoch().count(),
                                                      serial.fetch_add(1, std::memory_order_relaxed));
                }
                owner.time = epochNow();
                if (auto wrote = writeFileAtomic(record, encode(owner)); !wrote) return std::unexpected(wrote.error());
                held->record = std::move(record);
                return std::optional<MachineLease>{MachineLease{std::move(held)}};
            }
            if (mode == LeaseMode::shared) intent.lock = FileLock{};
        }

        if (Clock::now() >= deadline) return std::optional<MachineLease>{};
        if (intent.lock.isHeld() && intent.record.empty()) {
            auto record = sidecar(*path, ".writer.owner");
            if (auto wrote = writeFileAtomic(record, encode(owner)); !wrote) return std::unexpected(wrote.error());
            intent.record = std::move(record);
        }
        if (wait.onWait) wait.onWait(readOwners(*path));
        std::this_thread::sleep_until(std::min(Clock::now() + 100ms, deadline));
        if (Clock::now() >= deadline) return std::optional<MachineLease>{};
    }
}

std::string describeLeaseOwner(const LeaseOwner& owner)
{
    const auto start = std::chrono::sys_seconds{std::chrono::seconds{static_cast<std::int64_t>(owner.time)}};
    auto message = std::format("held by {} ({}), pid {}, since {:%FT%T}Z, {}", owner.tool.empty() ? "another tool" : owner.tool,
                               owner.what, owner.pid, start, modeName(owner.mode));
    const auto& resources = owner.resources;
    const std::array labels{std::pair{"cores", &resources.cores}, std::pair{"memory bandwidth", &resources.memoryBandwidth},
                            std::pair{"GPU", &resources.gpu}, std::pair{"power state", &resources.powerState}};
    for (const auto& [label, value] : labels) {
        if (!value->empty()) message += std::format(", {}: {}", label, *value);
    }
    return oneLine(message) + ". Wait for it to finish or stop it to release the lease.";
}

}  // namespace sub0platform
