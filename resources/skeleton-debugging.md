# Skeleton stream debugging

Install and enable Diagnostics through the extension manager. It has no graph node.

To test a real exporter, run Verify skeleton UDP stream with its listen address and port. A packet is insufficient: success requires complete decoded frames. Invalid packets, incomplete chunked frames and port binding failures are reported.

To test a graph without a game, deploy UDP In -> Skeleton Decoder -> visualization, then run Send simulated skeleton stream to UDP In's address and port. The simulator sends two bones named Root and Tip with a sinusoidal Tip position. The stream uses SDK-compatible JSON skeleton packets. Start the receiver before sending. Sending counts do not prove receiving or graph processing; inspect the receiver's monitor. The simulator and verifier can run concurrently. Start the simulator, leave it running, and select the verifier or switch to Graph to inspect the stream. Switching pages does not stop the sender. A verifier and UDP In cannot bind the same address and port at the same time.

Simulation requires confirmation, defaults to loopback, runs until Stop by default, emits at most 120 FPS, and can be stopped through the task manager. An optional explicit duration supports bounded runs up to 60 seconds. Keep physical outputs disabled while testing synthetic input.
