## v1.0.0 (2026-06-04)

### 🚨 Breaking changes

- **logger**: Accept variadic args in output methods *(Frantisek Hrbata - 8af378b)*
- EspLogBase / EspLog logging method signatures changed. *(Frantisek Hrbata - 8af378b)*
- The note prefix is now uppercase (Note -> NOTE). *(Peter Dragun - 4f98a6f)*
- Custom logger subclasses must implement the new `hint` method. *(Peter Dragun - 2ca600e)*

### ✨ New Features

- **logger**: add log.counter() for unbounded live progress *(Peter Dragun - 3af2c91)*
- **logger**: humanise progress M/N totals with unit='B' *(Peter Dragun - 8123f39)*
- **logger**: Add stage collapse functionality *(Peter Dragun - 8b2f22f)*
- **logger**: Add hint method to logger interface *(Peter Dragun - 2ca600e)*

### 🐛 Bug Fixes

- **logger**: Prevent console reassignment from capturing output *(Peter Dragun - 0789137)*
- Create EspLog singleton on demand in log proxy *(Peter Dragun - c2e29df)*
- Clarify logger does not escape text *(Peter Dragun - e149996)*
- Update note prefix to be uppercase *(Peter Dragun - 4f98a6f)*
- Add ASCII fallback for progress bars *(Peter Dragun - ce4c095)*
- Rename ESPRESSIF_IDE_WS to ESP_IDE_WS for consistency *(Peter Dragun - dc064e7)*

### 📖 Documentation

- Add quick start guide and simple examples to README *(Peter Dragun - d16ca6f)*


## v0.2.0 (2026-05-26)

### ✨ New Features

- **rom**: add ROM ELF path resolution *(Peter Dragun - b9f57a1)*
- **cli**: Extend cli types and options *(Peter Dragun - 4ae5cba)*
- **serial**: Add flow control support for CP2102C adapters *(Peter Dragun - 51d27c5)*
- **cli**: Add Click parameter types *(Peter Dragun - ea8678c)*
- **serial**: Add serial port discovery and reset sequences *(Peter Dragun - 23c53cc)*
- **config**: Add ToolConfig for INI config file loading *(Peter Dragun - dfd3159)*
- **ws**: Add IDE WebSocket transport and exception reporting *(Peter Dragun - 7dee356)*
- **logger**: Add first version of the logging library *(Peter Dragun - 770dd58)*
- **errors**: Add common error hierarchy *(Peter Dragun - 54c7d35)*
- **constants**: Add hardware and serial constants *(Peter Dragun - 568357c)*
- Add progress bar support *(Peter Dragun - be6cc65)*

### 📖 Documentation

- **skill**: Add migration skill for AI coding agents *(Peter Dragun - c252465)*


## v0.1.3 (2026-02-20)

### 🐛 Bug Fixes

- **github**: use correct underscore in tarball glob pattern in release_draft.yml *(copilot-swe-agent[bot] - a60bdf4)*


## v0.1.2 (2026-02-20)

### 🐛 Bug Fixes

- **github**: Create release drafts automatically *(Roland Dobai - d5f9c8b)*


## v0.1.1 (2026-02-19)

### 🐛 Bug Fixes

- prepare the initial release 0.1.1 *(Roland Dobai - d288574)*
