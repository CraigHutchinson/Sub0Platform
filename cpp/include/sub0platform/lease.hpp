#pragma once
/// @file lease.hpp
/// Per-user machine leases shared with Sub0Platform's Python package.

#include <chrono>
#include <cstdint>
#include <expected>
#include <filesystem>
#include <functional>
#include <memory>
#include <optional>
#include <string>
#include <vector>

#include "sub0platform/error.hpp"

namespace sub0platform {

/// Access to the machine under ADR 0005.
enum class LeaseMode { shared, exclusive };

/// Optional resource descriptions displayed while this job holds a lease.
struct LeaseResources
{
    std::string cores{};
    std::string memoryBandwidth{};
    std::string gpu{};
    std::string powerState{};
};

/// A diagnostic snapshot from a lease holder's owner record.
struct LeaseOwner
{
    std::int64_t pid = 0;
    double time = 0;  ///< UTC seconds since the Unix epoch.
    std::string what;
    std::string tool;
    LeaseMode mode = LeaseMode::exclusive;
    LeaseResources resources;
};

/// A caller's wait budget and the behavior on contention.
struct LeaseWait
{
    /// Zero attempts once. Sub0Platform uses a monotonic clock for a positive budget.
    std::chrono::milliseconds timeout{};
    /// Runs synchronously before retries. Keep it short. The lease may be busy before a holder publishes its record.
    std::function<void(const std::vector<LeaseOwner>&)> onWait;
};

/// A move-only machine lease. Destruction removes its owner record and releases the file lock.
class MachineLease
{
public:
    MachineLease(MachineLease&&) noexcept;
    MachineLease& operator=(MachineLease&&) noexcept;
    MachineLease(const MachineLease&) = delete;
    MachineLease& operator=(const MachineLease&) = delete;
    ~MachineLease();

    /// Acquires the machine lease. A waiting exclusive caller with writer intent excludes new shared callers.
    /// @param mode The requested access.
    /// @param tool A human-readable tool name in UTF-8.
    /// @param what The job the tool is performing in UTF-8.
    /// @param lockFile An explicit path for an isolated installation or test. An empty path uses defaultLockFile().
    /// @param wait The timeout and optional callback.
    /// @param resources UTF-8 resource descriptions for reports.
    /// @return A held lease, an empty optional when busy at the deadline, or a platform error.
    [[nodiscard]] static std::expected<std::optional<MachineLease>, PlatformError> acquire(
        LeaseMode mode, std::string tool, std::string what, const std::filesystem::path& lockFile = {},
        const LeaseWait& wait = {}, LeaseResources resources = {});

    /// Resolves the same per-user machine.lock path as the Python lease, without creating directories.
    /// @return The lock path or the platform error.
    [[nodiscard]] static std::expected<std::filesystem::path, PlatformError> defaultLockFile();

    /// Reads live diagnostic records. The OS lock determines whether the machine is busy.
    /// @param lockFile The machine lock path.
    /// @return A snapshot of holder records or the writer waiting for the lease if no holder record is available.
    [[nodiscard]] static std::vector<LeaseOwner> readOwners(const std::filesystem::path& lockFile);

private:
    struct Held;
    explicit MachineLease(std::unique_ptr<Held> held) noexcept;
    std::unique_ptr<Held> held_;
};

/// Formats a holder as a one-line diagnostic with the action that releases the lease.
/// @param owner A holder record.
/// @return The message in UTF-8.
[[nodiscard]] std::string describeLeaseOwner(const LeaseOwner& owner);

}  // namespace sub0platform
