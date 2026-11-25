#pragma once
/// @file dirs.hpp
/// Per-user application directories.

#include <expected>
#include <filesystem>
#include <string_view>

#include "sub0platform/error.hpp"

namespace sub0platform {

/// Finds the local state path for logs, history, and locks, following the same convention as Python's dirs.state.
/// @param app A single application directory name in UTF-8.
/// @return The application path, or a platform error if the user's state root cannot be found.
/// @note Does not create directories. Read environment overrides before modifying the process environment.
[[nodiscard]] std::expected<std::filesystem::path, PlatformError> stateDirectory(std::string_view app);

}  // namespace sub0platform
