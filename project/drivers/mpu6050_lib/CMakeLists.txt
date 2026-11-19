project(CFE_MPU6050_LIB C)

# Create the app module
add_cfe_app(mpu6050_lib fsw/src/mpu6050_lib.c)

# The API to this library (which may be invoked/referenced from other apps)
# is stored in fsw/public_inc.  Using "target_include_directories" is the 
# preferred method of indicating this (vs. directory-scope "include_directories").
target_include_directories(mpu6050_lib PUBLIC fsw/public_inc)

if (ENABLE_UNIT_TESTS)
  add_subdirectory(ut-stubs)
  add_subdirectory(unit-test)
endif (ENABLE_UNIT_TESTS)



# Sensor registers use the selected board's Linux I2C transport.
add_cfe_app_dependency(mpu6050_lib linux_i2c_lib)
