##################################################################
#
# Coverage Unit Test build recipe
#
# This CMake file contains the recipe for building the sample unit tests.
# It is invoked from the parent directory when unit tests are enabled.
#
##################################################################

#
# NOTE on the subdirectory structures here:
#
# - "inc" provides local header files shared between the coveragetest,
#    wrappers, and overrides source code units
# - "coveragetest" contains source code for the actual unit test cases
#    The primary objective is to get line/path coverage on the FSW
#    code units.
#

# Use the UT assert public API, and allow direct
# inclusion of source files that are normally private
include_directories(../fsw/src)
include_directories(${CMAKE_CURRENT_SOURCE_DIR}/inc)

add_cfe_coverage_stubs(hal_temp
  stubs/hal_temp_global_stubs.c
  stubs/hal_temp_stubs.c
  stubs/hal_temp_cmds_stubs.c
  stubs/hal_temp_dispatch_stubs.c
  stubs/hal_temp_utils_stubs.c
)

add_library(hal_temp_ut_common STATIC
    common/eventcheck.c
    common/setup.c
)

target_include_directories(hal_temp_ut_common PUBLIC common)
target_link_libraries(hal_temp_ut_common core_api ut_assert)


# Generate a dedicated "testrunner" executable for each test file
# Accomplish this by cycling through all the app's source files, there must be
# a *_tests file for each
foreach(SRCFILE ${APP_SRC_FILES})

    # Get the base sourcefile name as a module name without path or the
    # extension, this will be used as the base name of the unit test file.
    get_filename_component(UNIT_NAME "${SRCFILE}" NAME_WE)

    # Use the module name to make the test name by adding _tests to the end
    set(TESTS_NAME "coveragetest_${UNIT_NAME}")

    # Make the test sourcefile name with unit test path and extension
    set(TESTS_SOURCE_FILE "${CMAKE_CURRENT_SOURCE_DIR}/coveragetest/${TESTS_NAME}.c")

    # Create the coverage test executable
    add_cfe_coverage_test(hal_temp "${UNIT_NAME}" "${TESTS_SOURCE_FILE}" "../${SRCFILE}")
    add_cfe_coverage_dependency(hal_temp "${UNIT_NAME}" hal_temp)
    target_link_libraries(coverage-hal_temp-${UNIT_NAME}-testrunner coverage-hal_temp-stubs hal_temp_ut_common)

endforeach()



# The hal_temp uses library functions provided by sample_lib so must be linked
# with the sample_lib stub library (this is mainly just an example of how this
# can be done).
add_cfe_coverage_dependency(hal_temp hal_temp_cmds sample_lib)
