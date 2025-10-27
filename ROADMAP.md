## Roadmap

- **Enhance System Tray Icon**
  - Add dynamic status indicators (e.g., "Ready", "Thinking", "Speaking", "Error").
  - Implement animations for activity (e.g., pulsing, color shifts).
  - Support rich color cues to reflect real-time state changes (idle, active, error, paused, etc.).

- **Decouple UI and Logic**
  - Use the `AbstractCore` server to separate all application logic and processing from the user interface.

- **Unified Experience: Desktop & Web**
  - Serve both the system tray message bubble *and* a full-featured web interface for enhanced capability and better usability.

- **Advanced Agent Architecture**
  - Transition from basic LLM with tools (`AbstractCore`) to the more powerful `AbstractAgent` architecture, enabling richer interactions and tool use.

- **Media & Repository Integration**
  - Add support for media file handling and enable indexing/searching of entire code repositories for context-aware responses.

  - Need to haandle multiple sessions
    - crucial : freedom to switch from discussion to discussion

- fix session
- system prompt
- give the voice of hal9000
- changing speed or voice ? (eg french voice)

Improve doc with nice visuals