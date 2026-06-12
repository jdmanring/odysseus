# Documentation Templates

To ensure consistency across the new `/docs` architecture, the following templates will be used for all new content.

## 1. User Guide Template
**Purpose:** To enable a human user to achieve a specific goal using the UI.
**Focus:** Action-oriented, visual, and outcome-driven.

### Template:
`# [Feature/Operation Name]`
`## Goal`
`Brief description of what the user will achieve.`

`## Prerequisites`
`- [ ] Requirement 1 (e.g., "Must have a model served in the Cookbook")`
`- [ ] Requirement 2`

`## Step-by-Step Instructions`
`1. **[Action]**: [Instruction] (UI Element: #id)`
`2. **[Action]**: [Instruction] (UI Element: #id)`
`3. **[Action]**: [Instruction]`

`## Expected Result`
`Describe what happens after the steps are completed.`

`## Troubleshooting / Tips`
`- **Common Issue**: [Description] $\rightarrow$ **Solution**: [Fix]`
`- **Pro Tip**: [Shortcut or efficiency gain]`

---

## 2. AI Ops Guide Template
**Purpose:** To provide the AI model with a definitive reference for using its tools without hallucination.
**Focus:** Precision, constraints, and logic.

### Template:
`# Tool: [Tool Name]`
`## Purpose`
`What this tool does and the specific problem it solves.`

`## Input Specification`
`| Parameter | Type | Required | Description |`
`| :--- | :--- | :--- | :--- |`
`| param_1 | string | Yes | [Description] |`
`| param_2 | boolean | No | [Description] |`

`## Expected Output`
`Describe the structure and content of the return value.`

`## The "Golden Rule"`
`Exact condition under which this tool MUST be used, and when to avoid it in favor of [Alternative Tool].`

`## Failure & Recovery`
`- **Error A**: [Description] $\rightarrow$ **Recovery**: [Corrective Action]`

---

## 3. Technical Reference Template
**Purpose:** To provide a developer with a blueprint of the system's internals.
**Focus:** Architecture, data flow, and codebase mapping.

### Template:
`# Component: [Component Name]`
`## Responsibility`
`The primary role of this component in the overall system.`

`## Architecture & Data Flow`
`[Diagram or bulleted list showing: Source $\rightarrow$ Process $\rightarrow$ Destination]`

`## Integration Points`
`- **UI Trigger**: [UI Element / Event]`
`- **API Endpoint**: [Route / Method]`
`- **Dependencies**: [Other components]`

`## Implementation Details`
`- **Key Files**: [path/to/file.py], [path/to/file.js]`
`- **Core Logic**: [Brief explanation of the primary algorithm or pattern used]`

`## Maintenance Notes`
`Known technical debt or areas for future optimization.`