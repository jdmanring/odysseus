# AI FEATURE THEME

The Theme system is Odysseus's visual orchestration layer. It manages everything from core accessibility colors to advanced canvas-based background effects, ensuring the UI is both aesthetically flexible and functionally coherent.

## 1. Theme Definition & Color Theory

At its core, a theme is a collection of five primary hex colors that drive the entire CSS variable system:
- `--bg`: The main background color.
- `--fg`: The primary text/foreground color.
- `--panel`: The background for sidebars, modals, and cards.
- `--border`: The color for dividers and outlines.
- `--red`: The accent color (used for buttons, logos, and highlights).

### Preset vs. Custom Themes
- **Presets:** A library of built-in themes (e.g., `cyberpunk`, `midnight`, `forest`) provides instant visual identities.
- **Custom Themes:** Users can define up to 8 custom themes. These are stored in `localStorage` and synced to the server via `/api/prefs/custom-themes`.

### Automatic Harmony (Syntax Derivation)
The system does not require manual syntax colors. Instead, it uses an **HSL derivation engine** that calculates high-contrast, harmonious colors for code blocks based on the current theme:
- It analyzes the `fg` and `bg` luminosity to determine if the theme is "Dark" or "Light."
- It generates specific hex codes for `keywords`, `strings`, `comments`, `functions`, `numbers`, and `builtins` that are guaranteed to be legible against the theme's `code-bg`.

---

## 2. Advanced UI Customization

Beyond the primary colors, the system allows "Fine-Grained" control over specific UI components via the Advanced Picker.

### Component Mapping
Specific CSS variables are mapped to user-editable keys:
- **Chat Bubbles:** `userBubbleBg`, `aiBubbleBg`, `bubbleBorder`.
- **Sidebar:** `sidebarBg`, `brandColor`, `hamburgerColor`.
- **Input Area:** `inputBg`, `inputBorder`, `sendBtnBg`, `sendBtnHover`.
- **Code Blocks:** `codeBg`, `codeFg`.
- **Controls:** `toggleActive`.

---

## 3. Visual Effects & Aesthetics

Odysseus uses a hybrid approach to backgrounds, combining CSS and HTML5 Canvas.

### Background Patterns
The system supports various patterns, categorized by their implementation:
- **Static (CSS):** `dots` and `none`.
- **Dynamic (Canvas):** `rain`, `synapse`, `constellations`, `perlin-flow`, `petals`, `sparkles`, and `embers`.
- **Control Sliders:** For canvas patterns, users can adjust **Intensity** (opacity/frequency) and **Size** (scale of elements) in real-time.

### The "Frosted Glass" Mode
A global toggle (`body.theme-frosted`) applies a translucent, blurred backdrop filter to every panel, sidebar, and modal, creating a modern "Glassmorphism" effect.

---

## 4. Typography & Layout

### Font Management
- **Presets:** Support for `mono` (Fira Code), `sans`, and `serif`.
- **Custom Fonts:** The system can inject custom `@font-face` rules into the document head, allowing users to use local or hosted font files.

### Layout Density
The system manages spatial density via three modes:
- **Compact:** Reduced padding and margins for maximum information density.
- **Comfortable:** The default balanced spacing.
- **Spacious:** Increased padding for a more open, airy feel.

---

## 5. System Integrations

### Dynamic Favicons
To maintain visual consistency across the OS, the system generates **dynamic SVG favicons**. The SVG's `stroke` or `fill` is updated in real-time to match the theme's `--red` accent color. Additionally, the SVG shape changes based on the current route (e.g., a cookbook icon for `/cookbook`).

### Mobile Integration
The system updates the `<meta name="theme-color">` tag to match the current `--bg` color, ensuring the mobile browser's status bar and toolbar blend seamlessly with the application.