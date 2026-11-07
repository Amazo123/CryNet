/*
 * CryNet — the node <-> hub wire protocol.
 *
 * This is the hub's copy of a contract that already exists in the node's
 * sketch (firmware/node/node_crynet/node_crynet.ino).  Both sides were
 * written from the same table, and this component exists so that the hub
 * has the layout in a place a compiler can check, rather than as prose in
 * a comment.
 *
 * Frame (node -> hub):
 *
 *     0  0xC3            magic
 *     1  0x7E            magic
 *     2  type            1 = telemetry, 2 = burst fragment
 *     3  node id
 *     4  u16 burst seq
 *     6  u16 frag index
 *     8  u16 frag count
 *    10  u16 payload len
 *    12  u16 payload CRC-16/CCITT-FALSE
 *    14  payload
 *    ..  u16 frame CRC-16/CCITT-FALSE over everything above
 *
 * A request (hub -> node) is twelve bytes.  It has no payload, so it
 * carries only the CRC of its first ten bytes:
 *
 *     0  0xC3  1 0x7E  2 type=3  3 node id
 *     4  u16 burst seq   6 u16 first fragment   8 u16 fragment count
 *    10  u16 CRC-16/CCITT-FALSE over the first ten bytes
 *
 * The telemetry payload is sixteen bytes:
 *
 *     0  u32 rms x 1000          the node's 100 ms reading
 *     4  u16 window ms
 *     6  u8  flags
 *     7  u16 event level x 1000  the level the node triggers at
 *     9  u16 frozen rms x 1000   the level of the frozen window itself
 *    11  u8  floor x 1000        the node's noise floor
 *    12  u32 frozen crc          CRC-32 of the frozen window
 *
 * The event level is the node's own: it tracks the room's noise floor,
 * so the level that follows from it is the node's to decide, and the hub
 * triggers on the number the node reports.  A node that does not report
 * one (an older node) is given the hub's fixed level instead.
 */

#ifndef CRYNET_PROTO_H
#define CRYNET_PROTO_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define CRYNET_PROTO_MAGIC0        0xC3u
#define CRYNET_PROTO_MAGIC1        0x7Eu

#define CRYNET_PROTO_TYPE_TELEMETRY 1u
#define CRYNET_PROTO_TYPE_FRAGMENT  2u
#define CRYNET_PROTO_TYPE_REQUEST   3u
/* A heartbeat: the hub sends one every 100 ms so that its radio stays
 * awake.  A radio that is asleep between transmissions misses almost
 * everything the nodes send. */
#define CRYNET_PROTO_TYPE_HEARTBEAT 4u

/*
 * A resend request: the hub's list of the fragments of a burst that did
 * not arrive.  It carries the full fourteen-byte header and a payload,
 * and the payload is a bitmap — one bit per fragment, the bit set for
 * the fragments the hub is still missing.  Thirty-six bytes cover all
 * 286 fragments, so one request says everything that is missing however
 * scattered the losses are, and the whole frame is 54 bytes, well inside
 * the 255-byte ESP-NOW limit.
 *
 * The node answers by sending exactly the fragments whose bit is set,
 * out of the same frozen window and with the same sequence number, so
 * the fragments that did arrive are not sent again and the ones that did
 * not are now covered.
 */
#define CRYNET_PROTO_TYPE_RESEND   5u

#define CRYNET_PROTO_HEADER_BYTES  14u
#define CRYNET_PROTO_REQUEST_BYTES 12u

/* The bitmap in a resend request: one bit per fragment. */
#define CRYNET_PROTO_RESEND_BITMAP_BYTES \
    ((CRYNET_PROTO_FRAG_COUNT + 7u) / 8u)

/* ESP-NOW carries at most 255 bytes in one frame. */
#define CRYNET_PROTO_MAX_FRAME     255u
#define CRYNET_PROTO_MAX_PAYLOAD   (CRYNET_PROTO_MAX_FRAME - CRYNET_PROTO_HEADER_BYTES - 2u)

/* The signal contract: 2 s of 16 kHz mono int16. */
#define CRYNET_PROTO_WINDOW_SAMPLES 32000u
#define CRYNET_PROTO_WINDOW_BYTES   (CRYNET_PROTO_WINDOW_SAMPLES * 2u)

/* A fragment carries this many payload bytes; the node's frame is
 * 14 + 224 + 2 = 240 bytes, comfortably inside the ESP-NOW limit. */
#define CRYNET_PROTO_FRAG_PAYLOAD   224u
#define CRYNET_PROTO_FRAG_COUNT     \
    ((CRYNET_PROTO_WINDOW_BYTES + CRYNET_PROTO_FRAG_PAYLOAD - 1u) / CRYNET_PROTO_FRAG_PAYLOAD)

/* The telemetry payload is 16 bytes. */
#define CRYNET_PROTO_TELEMETRY_BYTES 16u

/* The radio-counter tier: the same 16 bytes, then the node's own radio
 * counters — the frames it handed to the radio, the frames the radio
 * refused, the frames that actually left it, and the number of times it
 * had to wait for the radio to have room.
 *
 * These are the counters that say where a burst went.  A node that hands
 * over all 286 fragments and sees only a few of them come back has lost
 * them in the air; a node whose radio refused them has a queue that is
 * too small for the burst.  The hub cannot tell the two apart from the
 * fragments alone, and the difference is the difference between moving
 * a cot and rewriting a radio's pacing.
 *
 * There was a battery tier between this one and the base tier — the
 * node's cell voltage, in two bytes.  It is gone (D-83): the cots do
 * not measure their cells, so the tier would only have carried zeroes,
 * and the counters moved down to fill the gap. */
#define CRYNET_PROTO_TELEMETRY_BYTES_COUNTERS \
    (CRYNET_PROTO_TELEMETRY_BYTES + 16u)

/* The payload a node flashed before the battery tier was removed sent:
 * the same bytes, plus the battery voltage, plus the counters.  The hub
 * still reads it, so a node that has not been reflashed yet does not
 * turn the hub's counters into noise while the units are being
 * reflashed one at a time. */
#define CRYNET_PROTO_TELEMETRY_BYTES_OLD_COUNTERS \
    (CRYNET_PROTO_TELEMETRY_BYTES + 2u + 16u)

/* The payload an older node sent: the same fields, without the event
 * level, the window's own level or the noise floor, and with the CRC
 * four bytes earlier. */
#define CRYNET_PROTO_TELEMETRY_BYTES_LEGACY 12u

/* Telemetry flags. */
#define CRYNET_PROTO_FLAG_BURST_READY   0x01u  /* the node has a frozen window  */
#define CRYNET_PROTO_FLAG_EVENT         0x02u  /* the node's event level is crossed */
#define CRYNET_PROTO_FLAG_WINDOW_FULL   0x04u  /* the live window holds 2 s     */

/* CRC-16/CCITT-FALSE: polynomial 0x1021, init 0xFFFF, no reflection. */
uint16_t crynet_proto_crc16(const uint8_t *data, size_t len);

/*
 * CRC-32, the IEEE 802.3 one: reflected, polynomial 0xEDB88320, init
 * 0xFFFFFFFF, final XOR 0xFFFFFFFF — the same function zlib's crc32()
 * computes.  The node puts this over its frozen window and advertises it
 * in the telemetry; the hub puts it over the window it reassembles from
 * the radio.  The two agreeing is the proof that the audio crossed the
 * link unchanged.
 */
uint32_t crynet_proto_crc32(const uint8_t *data, size_t len);

/*
 * Build a frame into `out`, which must have room for CRYNET_PROTO_MAX_FRAME
 * bytes.  Returns the total length including the trailing frame CRC, or 0
 * if the payload is too long.  A request frame (type 3) is built with the
 * twelve-byte layout; every other type uses the full header.
 */
size_t crynet_proto_build(uint8_t *out,
                           uint8_t type,
                           uint8_t node_id,
                           uint16_t seq,
                           uint16_t frag,
                           uint16_t frag_count,
                           const uint8_t *payload,
                           uint16_t payload_len);

/* Parse results. */
#define CRYNET_PROTO_BAD_FRAME    (-1)  /* malformed, or the frame CRC failed  */
#define CRYNET_PROTO_BAD_PAYLOAD  (-2)  /* the frame is sound, the payload is not */

/*
 * Parse a frame received from the radio.  On success the payload length is
 * returned (0 for a request) and the out parameters are filled in; for a
 * request, `payload` is set to NULL.  On failure one of the CRYNET_PROTO_BAD_*
 * codes is returned.
 */
int crynet_proto_parse(const uint8_t *data,
                        size_t len,
                        uint8_t *type,
                        uint8_t *node_id,
                        uint16_t *seq,
                        uint16_t *frag,
                        uint16_t *frag_count,
                        const uint8_t **payload);

/* Decode a telemetry payload. */
typedef struct {
    float    rms;        /* the node's 100 ms RMS, in full-scale units */
    uint16_t window_ms;  /* the length of the node's window           */
    uint8_t  flags;
    /* The level the node triggers at, in full-scale units.  Zero means
     * the node did not report one. */
    float    event_rms;
    /* The level of the node's frozen window itself, in full-scale
     * units: what the model will be shown, as opposed to the live
     * reading beside it. */
    float    frozen_rms;
    /* The node's noise floor, in full-scale units. */
    float    floor_rms;
    uint32_t frozen_crc; /* CRC-32 of the node's frozen window, 0 if none */
    /* The node's radio counters.  Zero means the node did not report
     * them: its firmware predates the field. */
    uint32_t frames_sent;   /* frames handed over to the radio   */
    uint32_t frames_lost;   /* frames the radio refused outright  */
    uint32_t frames_acked;  /* frames that actually left the radio */
    uint32_t radio_full;    /* times the radio had no room        */
} crynet_proto_telemetry_t;

bool crynet_proto_decode_telemetry(const uint8_t *payload,
                                   size_t len,
                                   crynet_proto_telemetry_t *out);

#ifdef __cplusplus
}
#endif

#endif /* CRYNET_PROTO_H */
