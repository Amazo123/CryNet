# CryNet hub — ESP-IDF project
#
# The vendored dependencies (the Espressif TFLite Micro port and ESP-NN)
# live in components/, next to the CryNet components, rather than in a
# separate EXTRA_COMPONENT_DIRS. That placement is deliberate:
#
#   PlatformIO does not build ESP-IDF components with IDF's own ninja
#   build; it re-compiles them with SCons. When it does that it derives
#   each object file's name from the SOURCE BASENAME, unless the source
#   lives inside the ESP-IDF framework directory or inside the project
#   directory — in those two cases it keeps the relative path. The TFLite
#   Micro port has twelve pairs of sources that share a basename
#   (common.cc, kernel_util.cc, circular_buffer.cc, and so on), so a
#   component sitting outside the project tree fails to build with
#   "Multiple ways to build the same target were specified for
#   .../circular_buffer.cc.o". Keeping the components inside the project
#   directory makes the relative paths distinct and the build succeed.
#
#   The consequence for the rest of the project: nothing else may set
#   EXTRA_COMPONENT_DIRS. PlatformIO passes its own
#   -DEXTRA_COMPONENT_DIRS:PATH=<project>/src on the cmake command line so
#   that the folder holding the application sources is registered as a
#   component, and a plain `set(EXTRA_COMPONENT_DIRS ...)` here would
#   shadow that and break the main target.
#
# The exact revisions of the vendored components are pinned in
# firmware/tools/fetch_deps.sh.

cmake_minimum_required(VERSION 3.16)

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(crynet_hub)
