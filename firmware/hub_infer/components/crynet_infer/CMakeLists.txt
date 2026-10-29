idf_component_register(
    SRCS "crynet_infer.cpp"
    INCLUDE_DIRS "include"
    REQUIRES crynet_model
    PRIV_REQUIRES esp-tflite-micro esp_hw_support
)
