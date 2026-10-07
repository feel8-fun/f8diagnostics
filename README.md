# Diagnostics

An optional, versioned debugging toolkit for Feel8 extensions. The package name is `f8diagnostics` and the extension ID is `diagnostics`. Its scope includes streams, protocols, and runtime integrations; skeleton UDP tools are the first tools in the collection. Runtime code depends on the SDK, without importing Studio or PyEngine.

## Tools

- **Verify skeleton UDP stream**: decode SDK-compatible packets, assemble complete frames, and report malformed packets or incomplete chunks.
- **Send simulated skeleton stream**: continuously emit an animated Root/Tip skeleton. Leave duration blank to run until Stop. An optional explicit duration allows a bounded run up to 60 seconds; FPS is limited to 120.

Install and enable Diagnostics in the extension manager, then select its tools in Tools. It is not preinstalled. No serial scanner is included.

Simulation and verification allow concurrent execution. Start the simulator, switch to verification or Graph, and inspect the receiving stream. The sender stays running until Stop or Studio shutdown. A verifier and a graph UDP In node cannot bind the same address and port simultaneously; use one receiver at a time. Sending alone does not prove receiver delivery.

## Development

The extension follows the generic `f8toolInput/1` stdin and `f8toolResult/1` stdout protocol. Exceptions and tracebacks go to stderr. The source manifest declares its own `diagnostics` workspace environment, which Platform prepares from this package's Pixi manifest and lock.

For independent development:

```sh
git clone https://github.com/feel8-fun/f8sdk.git .sdk
git -C .sdk checkout 16ba9e68434d0a0ed419a1a691c924c2e12590a8
pixi install --locked -e diagnostics
pixi run --locked -e diagnostics check
pixi run --locked -e diagnostics test
pixi run --locked -e diagnostics basedpyright -p pyrightconfig.json
pixi run --locked -e diagnostics bundle
```

The pinned SDK revision matches CI on Linux and Windows and the committed lock file. Keep `.sdk` as that Git checkout; copying a newer SDK can change local package dependency metadata and make locked installation fail. Back up an existing incorrect input before replacing it, then retry Prepare in Platform after installation succeeds.

`pixi run --locked -e diagnostics bundle` creates `build/extension.zip` and its SHA-256 file for the shared-runtime installer. The source manifest declares a workspace runtime; the publisher rewrites it to the generic shared runtime in the ZIP. The Studio integration tests, including persistent send/verify concurrency and stopping, remain in the Studio repository.
