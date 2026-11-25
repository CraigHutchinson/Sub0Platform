# The library's modules: one public header include/sub0platform/<module>.hpp each. This list is the single source for the build (CMakeLists.txt
# makes one static library from it) and for the include check (CheckLayers.cmake). A module's sources are src/<module>.cpp and, when the
# operating system differs, src/<module>_posix.cpp or src/<module>_win32.cpp.
set(SUB0PLATFORM_MODULES error process proc host file net ipc wait dirs lease)

# Headers private to the backends. Public headers never include them.
set(SUB0PLATFORM_PRIVATE_HEADERS util.hpp posix_util.hpp win32_util.hpp)
