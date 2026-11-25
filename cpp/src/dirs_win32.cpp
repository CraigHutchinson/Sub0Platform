#include <string>

#include "sub0platform/dirs.hpp"
#include "sub0platform/proc.hpp"
#include "win32_util.hpp"

namespace sub0platform {

std::expected<std::filesystem::path, PlatformError> stateDirectory(std::string_view app)
{
    namespace fs = std::filesystem;
    const auto local = getEnvironment("LOCALAPPDATA").value_or("");
    if (!local.empty()) return fs::path{win32::widen(local)} / win32::widen(app);

    auto home = getEnvironment("USERPROFILE").value_or("");
    if (home.empty()) {
        const auto homePath = getEnvironment("HOMEPATH").value_or("");
        if (!homePath.empty()) home = getEnvironment("HOMEDRIVE").value_or("") + homePath;
    }
    if (home.empty()) {
        return std::unexpected(PlatformError{"find user state directory", ERROR_PATH_NOT_FOUND, "user profile directory is unavailable"});
    }
    return fs::path{win32::widen(home)} / L"AppData" / L"Local" / win32::widen(app);
}

}  // namespace sub0platform
