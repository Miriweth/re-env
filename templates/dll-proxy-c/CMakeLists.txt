cmake_minimum_required(VERSION 3.24)
project(version_proxy C)

if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

include(FetchContent)
FetchContent_Declare(minhook
    GIT_REPOSITORY https://github.com/TsudaKageyu/minhook
    GIT_TAG v1.3.4)
FetchContent_MakeAvailable(minhook)

add_library(version SHARED src/dllmain.c src/proxy.c src/version.def)
set_target_properties(version PROPERTIES PREFIX "" SUFFIX ".dll")
target_link_libraries(version PRIVATE minhook)
# Static: the game must not need libgcc/winpthread DLLs next to it.
target_link_options(version PRIVATE -static -static-libgcc)
