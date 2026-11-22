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

add_cfe_coverage_stubs(hal_mag
  stubs/hal_mag_global_stubs.c
  stubs/hal_mag_stubs.c
  stubs/hal_mag_cmds_stubs.c
  stubs/hal_mag_dispatch_stubs.c
  stubs/hal_mag_utils_stubs.c
)

add_library(hal_mag_ut_common STATIC
    common/eventcheck.c
    common/setup.c
)

target_include_directories(hal_mag_ut_common PUBLIC common)
target_link_libraries(hal_mag_ut_common core_api ut_assert)


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
    add_cfe_coverage_test(hal_mag "${UNIT_NAME}" "${TESTS_SOURCE_FILE}" "../${SRCFILE}")
    add_cfe_coverage_dependency(hal_mag "${UNIT_NAME}" hal_mag)
    target_link_libraries(coverage-hal_mag-${UNIT_NAME}-testrunner coverage-hal_mag-stubs hal_mag_ut_common)

endforeach()



# The hal_mag uses library functions provided by sample_lib so must be linked
# with the sample_lib stub library (this is mainly just an example of how this
# can be done).
add_cfe_coverage_dependency(hal_mag hal_mag_cmds sample_lib)
