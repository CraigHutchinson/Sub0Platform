cmake_minimum_required(VERSION 3.24)
# Sub0Platform's C++ library. Works as the top-level project (tests on by default) and as a subdirectory or CPM package with
# SOURCE_SUBDIR cpp (tests off by default, nothing else changed in the consumer's build).
project(Sub0Platform LANGUAGES CXX)

include(cmake/Modules.cmake)

option(SUB0PLATFORM_BUILD_TESTS "Build the platform tests and register them with CTest" ${PROJECT_IS_TOP_LEVEL})
option(SUB0PLATFORM_INSTALL "Install the library, its headers and a package config" ${PROJECT_IS_TOP_LEVEL})

set(SUB0PLATFORM_STRICT -Wall -Wextra -Werror)
if(CMAKE_CXX_COMPILER_ID STREQUAL "GNU")
  # Clang is the strict reference compiler. GCC 15 adds two flow-based diagnostics that are not errors here, so GCC can still build:
  # both stay visible as warnings (the same two Sub0Squad keeps as warnings).
  list(APPEND SUB0PLATFORM_STRICT -Wno-error=array-bounds -Wno-error=format-truncation)
endif()

if(WIN32)
  set(SUB0PLATFORM_OS win32)
else()
  set(SUB0PLATFORM_OS posix)
endif()

set(SUB0PLATFORM_SOURCES "")
foreach(module ${SUB0PLATFORM_MODULES})
  foreach(candidate src/${module}.cpp src/${module}_${SUB0PLATFORM_OS}.cpp)
    if(EXISTS ${CMAKE_CURRENT_SOURCE_DIR}/${candidate})
      list(APPEND SUB0PLATFORM_SOURCES ${candidate})
    endif()
  endforeach()
endforeach()

add_library(sub0platform STATIC ${SUB0PLATFORM_SOURCES})
add_library(Sub0Platform::sub0platform ALIAS sub0platform)
set_target_properties(sub0platform PROPERTIES CXX_STANDARD 23 CXX_STANDARD_REQUIRED ON CXX_EXTENSIONS OFF)
target_include_directories(sub0platform PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
target_include_directories(sub0platform PRIVATE src)
target_compile_options(sub0platform PRIVATE ${SUB0PLATFORM_STRICT})
if(WIN32)
  # The Windows backends split command lines with CommandLineToArgvW (shell32), use Winsock (ws2_32) and name the user (advapi32).
  target_link_libraries(sub0platform PUBLIC shell32 ws2_32 advapi32)
  # libstdc++ on Windows keeps std::print's console output in libstdc++exp; the same link Sub0Squad makes under MinGW.
  if(MINGW)
    target_link_libraries(sub0platform PUBLIC stdc++exp)
  endif()
endif()

if(SUB0PLATFORM_INSTALL)
  include(GNUInstallDirs)
  include(CMakePackageConfigHelpers)
  install(TARGETS sub0platform EXPORT Sub0PlatformTargets
    ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR})
  install(DIRECTORY include/ DESTINATION ${CMAKE_INSTALL_INCLUDEDIR})
  install(EXPORT Sub0PlatformTargets NAMESPACE Sub0Platform:: DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/Sub0Platform)
  configure_package_config_file(cmake/Sub0PlatformConfig.cmake.in
    ${CMAKE_CURRENT_BINARY_DIR}/Sub0PlatformConfig.cmake
    INSTALL_DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/Sub0Platform)
  install(FILES ${CMAKE_CURRENT_BINARY_DIR}/Sub0PlatformConfig.cmake
    DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/Sub0Platform)
endif()

if(SUB0PLATFORM_BUILD_TESTS)
  enable_testing()
  add_test(NAME layering COMMAND ${CMAKE_COMMAND} -DSRC_DIR=${CMAKE_CURRENT_SOURCE_DIR} -P ${CMAKE_CURRENT_SOURCE_DIR}/cmake/CheckLayers.cmake)

  # The children the process and proc tests start: one program, the same on every system.
  add_executable(platform_child tests/platform_child.cpp)
  target_link_libraries(platform_child PRIVATE sub0platform)
  target_compile_options(platform_child PRIVATE ${SUB0PLATFORM_STRICT})
  set_target_properties(platform_child PROPERTIES CXX_STANDARD 23 CXX_STANDARD_REQUIRED ON CXX_EXTENSIONS OFF)

  foreach(t process proc host file net wait)
    add_executable(test_platform_${t} tests/test_platform_${t}.cpp)
    target_link_libraries(test_platform_${t} PRIVATE sub0platform)
    target_compile_options(test_platform_${t} PRIVATE ${SUB0PLATFORM_STRICT} -g)   # line numbers when a test crashes
    target_compile_definitions(test_platform_${t} PRIVATE SUB0PLATFORM_CHILD="$<TARGET_FILE:platform_child>")
    add_dependencies(test_platform_${t} platform_child)
    set_target_properties(test_platform_${t} PROPERTIES CXX_STANDARD 23 CXX_STANDARD_REQUIRED ON CXX_EXTENSIONS OFF)
    add_test(NAME test_platform_${t} COMMAND test_platform_${t})
  endforeach()
endif()
