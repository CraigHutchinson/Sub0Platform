#include <cstdio>
#include <fstream>
#include <string>
#include <string_view>

#include "sub0platform/lease.hpp"
#include "sub0platform/testing/check.hpp"

using namespace sub0platform;
namespace fs = std::filesystem;

int child(std::string_view action, std::string_view mode, const fs::path& path)
{
    if (action == "read") {
        const auto owners = MachineLease::readOwners(path);
        if (owners.size() != 1 || owners.front().tool != "python" || owners.front().what != "serve \"examples\"\\\n" ||
            owners.front().resources.powerState != "AC") return 2;
        return 0;
    }
    auto lease = MachineLease::acquire(mode == "shared" ? LeaseMode::shared : LeaseMode::exclusive, "C++",
                                       "test holder", path, {}, LeaseResources{.gpu = "GPU 0"});
    if (!lease) {
        std::fprintf(stderr, "%s\n", lease.error().what().c_str());
        return 2;
    }
    if (!*lease) return 75;
    if (action == "hold") {
        std::puts("ready");
        std::fflush(stdout);
        (void)std::getchar();  // EOF or one byte releases the isolated fixture.
    }
    return 0;
}

int main(int argc, char** argv)
{
    if (argc == 4) return child(argv[1], argv[2], fs::path{argv[3]});
    const auto dir = makeTempDir("platform-lease");
    const auto path = dir / "machine.lock";
    const auto ownerFile = dir / "machine.lock.owner";

    std::ifstream vectors("lease_owner.jsonl", std::ios::binary);
    CHECK(vectors.is_open());
    int index = 0;
    for (std::string line; std::getline(vectors, line); ++index) {
        const auto at = line.find("123456789");
        if (at == std::string::npos) break;
        line.replace(at, 9, std::to_string(currentProcess()));
        CHECK(writeFile(ownerFile, line).has_value());
        const auto owners = MachineLease::readOwners(path);
        if (index < 2) {
            CHECK(owners.size() == 1);
            if (owners.empty()) continue;
            const auto& owner = owners.front();
            if (index == 0) {
                CHECK(owner.mode == LeaseMode::exclusive && owner.tool == "legacy");
                CHECK(owner.time == 0 && owner.what == "measure \"vectors\" \\ path");
            } else {
                CHECK(owner.mode == LeaseMode::shared && owner.tool == "engine \xf0\x9f\x9a\xb2");
                CHECK(owner.time == 1.25 && owner.what == "serve\nqueries");
                CHECK(owner.resources.gpu == "GPU 0" && owner.resources.powerState == "AC");
                CHECK(owner.resources.cores == "P0\xe2\x80\x93P3" && owner.resources.memoryBandwidth == "high");
                const auto message = describeLeaseOwner(owner);
                CHECK(message.find("1970-01-01T00:00:01Z, shared") != std::string::npos);
                CHECK(message.find("serve queries") != std::string::npos);
            }
        } else {
            CHECK(owners.empty());
        }
    }
    CHECK(index == 3);
    ::removeTree(dir);
    return finish();
}
