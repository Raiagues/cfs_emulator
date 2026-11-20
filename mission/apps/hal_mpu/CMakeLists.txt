project(CFE_HAL_MPU C)

if(CFE_EDS_ENABLED)
  message(FATAL_ERROR "Studio mission extensions require the non-EDS build profile.")
endif()

set(APP_SRC_FILES
  fsw/src/hal_mpu.c
  fsw/src/hal_mpu_cmds.c
  fsw/src/hal_mpu_utils.c
)

if (CFE_EDS_ENABLED)
  list(APPEND APP_SRC_FILES
    fsw/src/hal_mpu_eds_dispatch.c
  )
else()
  list(APPEND APP_SRC_FILES
    fsw/src/hal_mpu_dispatch.c
  )
endif()

list(APPEND APP_SRC_FILES
# APPGEN BEGIN SOURCES
    fsw/src/hal_mpu_components.c
    fsw/src/hal_mpu_user.c
    fsw/src/sensors/hal_mpu_sample_sensor.c
# APPGEN END SOURCES
)

# Create the app module
add_cfe_app(hal_mpu ${APP_SRC_FILES})

target_include_directories(hal_mpu PUBLIC fsw/inc)
# Include the public API from sample_lib to demonstrate how
# to call library-provided functions
add_cfe_app_dependency(hal_mpu sample_lib)

target_include_directories(hal_mpu PRIVATE fsw/src)
# APPGEN BEGIN DEPENDENCIES
add_cfe_app_dependency(hal_mpu linux_i2c_lib)
add_cfe_app_dependency(hal_mpu mpu6050_lib)
# APPGEN END DEPENDENCIES

# Add table
add_cfe_tables(hal_mpu fsw/tables/hal_mpu_tbl.c)

# If UT is enabled, then add the tests from the subdirectory
# Note that this is an app, and therefore does not provide
# stub functions, as other entities would not typically make
# direct function calls into this application.
if (ENABLE_UNIT_TESTS)
  add_subdirectory(unit-test)
endif (ENABLE_UNIT_TESTS)
