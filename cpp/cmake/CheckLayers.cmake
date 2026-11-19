# Include check for the Sub0Platform C++ library: the one-layer form of Sub0Squad's cmake/CheckLayers.cmake. The library is one layer, so
# the rules are about its edges rather than between layers:
#   - a quoted include in the library names a module (sub0platform/<module>.hpp) or a private backend header, nothing else of ours;
#   - a public header includes only other public headers and no operating-system header;
#   - every file in src/ and include/ belongs to a module, so none is silently left out of the build.
# Run as: cmake -DSRC_DIR=<cpp root> -P CheckLayers.cmake (without SRC_DIR it is an error, never a silent pass).
if(NOT SRC_DIR OR NOT EXISTS "${SRC_DIR}/src")
  message(FATAL_ERROR "layering check: pass -DSRC_DIR=<cpp root> (got '${SRC_DIR}')")
endif()
include("${CMAKE_CURRENT_LIST_DIR}/Modules.cmake")

set(systemHeader "^#include <((unistd|spawn|poll|signal|fcntl|dirent|termios|pty|netdb|pwd|grp|dlfcn|windows|winsock2|ws2tcpip|afunix|shellapi|tlhelp32|share|io)\\.h|csignal|(sys|arpa|netinet|linux)/[a-z_0-9]+\\.h)>")

file(GLOB_RECURSE publicHeaders "${SRC_DIR}/include/sub0platform/*.hpp")
file(GLOB sources "${SRC_DIR}/src/*.cpp" "${SRC_DIR}/src/*.hpp")
list(LENGTH publicHeaders publicCount)
list(LENGTH sources sourceCount)
if(publicCount EQUAL 0 OR sourceCount EQUAL 0)
  message(FATAL_ERROR "layering check: no sources found under ${SRC_DIR}")
endif()

set(bad "")

# A file in src/ belongs to a module (after dropping the backend suffix) or is a private header.
foreach(f ${sources})
  get_filename_component(name "${f}" NAME)
  get_filename_component(stem "${f}" NAME_WE)
  string(REGEX REPLACE "_(posix|win32)$" "" stem "${stem}")
  if(name IN_LIST SUB0PLATFORM_PRIVATE_HEADERS)
    continue()
  endif()
  if(NOT stem IN_LIST SUB0PLATFORM_MODULES)
    list(APPEND bad "src file not assigned to a module: ${name}")
  endif()
endforeach()

# Each public header is a module, and no module lacks its header.
foreach(m ${SUB0PLATFORM_MODULES})
  if(NOT EXISTS "${SRC_DIR}/include/sub0platform/${m}.hpp")
    list(APPEND bad "module has no public header: ${m}")
  endif()
endforeach()
foreach(f ${publicHeaders})
  file(RELATIVE_PATH rel "${SRC_DIR}/include/sub0platform" "${f}")
  if(rel MATCHES "^testing/")
    continue()
  endif()
  get_filename_component(stem "${f}" NAME_WE)
  if(NOT stem IN_LIST SUB0PLATFORM_MODULES)
    list(APPEND bad "public header not assigned to a module: ${rel}")
  endif()
endforeach()

# Quoted includes: the library's own headers only, and public headers stay public.
foreach(f ${sources} ${publicHeaders})
  file(RELATIVE_PATH rel "${SRC_DIR}" "${f}")
  file(STRINGS "${f}" lines REGEX "^#include \"")
  foreach(l ${lines})
    string(REGEX REPLACE "^#include \"([^\"]+)\".*" "\\1" inc "${l}")
    if(inc MATCHES "^sub0platform/([a-z_0-9]+)\\.hpp$")
      set(m "${CMAKE_MATCH_1}")
      if(NOT m IN_LIST SUB0PLATFORM_MODULES)
        list(APPEND bad "${rel} includes an unknown module: ${inc}")
      endif()
    elseif(inc MATCHES "^sub0platform/testing/check\\.hpp$")
      continue()
    elseif(inc IN_LIST SUB0PLATFORM_PRIVATE_HEADERS)
      if(rel MATCHES "^include/")
        list(APPEND bad "${rel} is public but includes the private header ${inc}")
      endif()
    else()
      list(APPEND bad "${rel} includes ${inc}, which is not part of the library")
    endif()
  endforeach()
endforeach()

# Public headers name no operating-system header: consumers of the API never see the platform's own types.
foreach(f ${publicHeaders})
  file(RELATIVE_PATH rel "${SRC_DIR}" "${f}")
  file(STRINGS "${f}" sys REGEX "${systemHeader}")
  if(sys)
    list(APPEND bad "${rel} includes an operating-system header (keep it in src/)")
  endif()
endforeach()

if(bad)
  string(REPLACE ";" "\n  " msg "${bad}")
  message(FATAL_ERROR "layering check failed:\n  ${msg}")
endif()
message(STATUS "layering ok (${sourceCount} library sources, ${publicCount} public headers, one layer)")
