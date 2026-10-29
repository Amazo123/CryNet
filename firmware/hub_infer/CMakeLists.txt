# CryNet hub — ESP-IDF project
#
# The TFLite Micro port is vendored under firmware/third_party and added
# to the build through EXTRA_COMPONENT_DIRS rather than the IDF component
# manager, so the build has no network dependency and the exact version
# used is pinned in git.
#
# firmware/tools/fetch_deps.sh clones the pinned revisions.

cmake_minimum_required(VERSION 3.16)

set(EXTRA_COMPONENT_DIRS
    "${CMAKE_CURRENT_LIST_DIR}/../third_party/esp-tflite-micro"
)

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(crynet_hub)
