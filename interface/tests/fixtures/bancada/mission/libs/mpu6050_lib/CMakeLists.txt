project(CFE_MPU6050_LIB C)

add_cfe_app(mpu6050_lib fsw/src/mpu6050_lib.c fsw/src/compat.c)
target_include_directories(mpu6050_lib PUBLIC fsw/public_inc)
add_cfe_app_dependency(mpu6050_lib hal_sensor linux_i2c_lib)
