#include <pwd.h>
#include <unistd.h>

#include <algorithm>
#include <cerrno>
#include <vector>

#include "posix_util.hpp"
#include "sub0platform/dirs.hpp"
#include "sub0platform/proc.hpp"

namespace sub0platform {

std::expected<std::filesystem::path, PlatformError> stateDirectory(std::string_view app)
{
    namespace fs = std::filesystem;
    const auto state = getEnvironment("XDG_STATE_HOME").value_or("");
    if (!state.empty()) return fs::path{state} / app;
    const auto home = getEnvironment("HOME").value_or("");
    if (!home.empty()) return fs::path{home} / ".local" / "state" / app;

    const long hint = ::sysconf(_SC_GETPW_R_SIZE_MAX);
    std::vector<char> buffer(static_cast<std::size_t>(std::max(hint, 1024L)));
    passwd entry{};
    passwd* found = nullptr;
    int error = 0;
    for (;;) {
        error = ::getpwuid_r(::getuid(), &entry, buffer.data(), buffer.size(), &found);
        if (error != ERANGE) break;
        buffer.resize(buffer.size() * 2);
    }
    if (error != 0 || !found || !found->pw_dir || !*found->pw_dir) {
        return std::unexpected(posix::sysError("find user state directory", error == 0 ? ENOENT : error));
    }
    return fs::path{found->pw_dir} / ".local" / "state" / app;
}

}  // namespace sub0platform
