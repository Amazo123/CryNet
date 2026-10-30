#
# Main component of the CryNet hub.
#
# The app is deliberately thin at this stage: Stage 2a is about proving
# that the front end and the model behave on the real chip, so the entry
# point runs the verification probes and reports measurements.  Stage 2c
# adds the radio: link_stage.c listens to the nodes and runs the windows
# they send through the verified front end.
#
idf_component_register(
    SRCS "main.c" "probes.c" "link_stage.c"
    INCLUDE_DIRS "."
    REQUIRES crynet_model crynet_dsp crynet_infer crynet_proto node_link esp_timer nvs_flash spi_flash
)
