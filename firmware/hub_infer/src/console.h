/*
 * CryNet hub — the bench console.
 *
 * The hub logs to the same UART it listens on, and until now it only
 * ever spoke.  This gives it a way to answer, so that the parts of the
 * system that can be checked without making a noise can be checked:
 *
 *   help              what the console understands
 *   status            the cots: their level, their window, their state
 *   alert <cot>       publish a test alert for that cot, as if it had
 *                     heard a cry -- the caregiver's phone buzzes and
 *                     the wearable shows it
 *   clear             take the test alert back
 *
 * The test alert is the reason the console exists.  The last unproven
 * link in the system was the BLE one: the hub published "a cry on cot
 * 1 at 100%" and the wearable was never attached to see it.  With this
 * command the whole BLE path -- the hub's publisher, the Bluetooth
 * link, the wearable's client and its display -- can be exercised at
 * any time, in any room, without waking anybody.
 *
 * The console is deliberately small: no history, no editing, no
 * commands that can change how the system behaves.  A line is read, a
 * word is looked up, and the answer is printed.
 */

#ifndef CONSOLE_H
#define CONSOLE_H

#ifdef __cplusplus
extern "C" {
#endif

/* Start the console task.  It reads the UART the hub logs to, so the
 * log and the console share the port -- a console line appears in the
 * log, and the log never disturbs a command. */
void console_start(void);

#ifdef __cplusplus
}
#endif

#endif /* CONSOLE_H */
