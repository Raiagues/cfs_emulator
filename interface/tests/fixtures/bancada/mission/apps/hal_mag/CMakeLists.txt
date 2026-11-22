project(CFE_HAL_MAG C)

if(CFE_EDS_ENABLED)
  message(FATAL_ERROR "Studio mission extensions require the non-EDS build profile.")
endif()

set(APP_SRC_FILES
  fsw/src/hal_mag.c
  fsw/src/hal_mag_cmds.c
  fsw/src/hal_mag_utils.c
)

if (CFE_EDS_ENABLED)
  list(APPEND APP_SRC_FILES
    fsw/src/hal_mag_eds_dispatch.c
  )
else()
  list(APPEND APP_SRC_FILES
    fsw/src/hal_mag_dispatch.c
  )
endif()

list(APPEND APP_SRC_FILES
# APPGEN BEGIN SOURCES
    fsw/src/hal_mag_components.c
    fsw/src/hal_mag_user.c
    fsw/src/sensors/hal_mag_sample_sensor.c
# APPGEN END SOURCES
)

# Create the app module
add_cfe_app(hal_mag ${APP_SRC_FILES})

target_include_directories(hal_mag PUBLIC fsw/inc)
# Include the public API from sample_lib to demonstrate how
# to call library-provided functions
add_cfe_app_dependency(hal_mag sample_lib)

target_include_directories(hal_mag PRIVATE fsw/src)
# APPGEN BEGIN DEPENDENCIES
add_cfe_app_dependency(hal_mag linux_i2c_lib)
add_cfe_app_dependency(hal_mag lsm303dlhc_mag_lib)
# APPGEN END DEPENDENCIES

# Add table
add_cfe_tables(hal_mag fsw/tables/hal_mag_tbl.c)

# If UT is enabled, then add the tests from the subdirectory
# Note that this is an app, and therefore does not provide
# stub functions, as other entities would not typically make
# direct function calls into this application.
if (ENABLE_UNIT_TESTS)
  add_subdirectory(unit-test)
endif (ENABLE_UNIT_TESTS)
