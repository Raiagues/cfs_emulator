project(CFE_LINUX_I2C_LIB C)

add_cfe_app(linux_i2c_lib fsw/src/linux_i2c_lib.c)
target_include_directories(linux_i2c_lib PUBLIC fsw/public_inc)
if(TARGETSYSTEM MATCHES "^native_")
    target_compile_definitions(linux_i2c_lib PRIVATE FLIGHT_STUDIO_NATIVE_I2C)
endif()
