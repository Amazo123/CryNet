#
# Main component of the CryNet hub.
#
# The app is deliberately thin at this stage: Stage 2a is about proving
# that the front end and the model behave on the real chip, so the entry
# point runs the verification probes and reports measurements. The radio,
# display and BLE layers arrive in later stages.
#
idf_component_register(
    SRCS "main.c" "probes.c"
    INCLUDE_DIRS "."
    REQUIRES crynet_model crynet_dsp crynet_infer esp_timer
)
