#
# The hub's ILI9341 panel and the state that is drawn on it.
#
idf_component_register(
    SRCS "ili9341.c" "hub_display.c"
    INCLUDE_DIRS "include"
    PRIV_INCLUDE_DIRS "."
    REQUIRES esp_driver_spi esp_driver_gpio
)
