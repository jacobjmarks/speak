<p align="center">
  <img src="docs/images/hero.png" alt="Speak: talk anywhere, it types" width="100%">
</p>

<h3 align="center">Talk anywhere. Speak types it for you, neatly, without your voice ever leaving your computer.</h3>


<p align="center">
  <a href="https://github.com/jacobjmarks/speak/releases"><b>Desktop builds</b></a>
  &nbsp;·&nbsp; Windows and macOS &nbsp;·&nbsp; Free and open source
</p>

---

## Why Speak

**🔒 Private.** Your voice is turned into text on your own computer. No account, no cloud, nothing uploaded.

**✈️ Works offline.** After a one-time download of the speech models, Speak needs no internet at all.

**⚡ Fast.** Words appear as you talk, and tidy text lands in your app the moment you stop.

**🌍 Multilingual.** 32 speech locales, including 19 transcription-ready locales. Speak detects the language, or you can choose a locale.

**💚 Open source.** Free, and every line is public. Nothing hidden about what happens to your voice.

**✍️ Writes like you meant it.** Punctuation, paragraphs and capitals are added for you. Ums, ahs and repeated words disappear. Change your mind mid-sentence ("Tuesday, no, Wednesday") and Speak writes what you meant.

**🖱️ Works in any app.** Email, chat, documents, browsers. If you can type there, you can speak there.

## How it works

1. Hold **Right Alt** wherever you want to type and talk, then let go. Or tap it once to start and again to stop. You can change the shortcut, or make it hold-only or tap-only, in Settings.
2. Speak. A small indicator shows it's listening, with your words appearing underneath.
3. Stop. Your text is tidied up and typed straight into the app you're using.

<p align="center">
  <img src="docs/images/overlay-light.png" alt="The listening indicator with live text" width="340">
</p>

## Install

1. Download the package for your OS from the [latest release](https://github.com/jacobjmarks/speak/releases): `Speak-<version>-windows-x64.exe` on Windows or `Speak-<version>-macos-arm64.zip` on macOS.
2. On macOS, open the app from Finder and approve it in **Privacy & Security** if Gatekeeper blocks it. Builds are unsigned and require this manual approval. On first launch, Speak shows a setup page for the three permissions it needs (Microphone, Input Monitoring, Accessibility); click Allow on each and it continues once all are granted.
3. Press the shortcut and start talking. The first dictation downloads the speech model (about 700 MB, once). Tidy-up models are 0.5 to 2.5 GB, chosen to suit your computer.

Speak can start with your computer and wait quietly in the system tray. You choose the first time you close the window. It keeps itself up to date (or just tells you, or doesn't check: your choice).

## Screenshots

<p align="center">
  <img src="docs/images/dictate-light.png" alt="Dictate page" width="49%">
  <img src="docs/images/settings-dark.png" alt="Settings page in dark mode" width="49%">
</p>

## Make it yours

- **Your shortcut**: any key combination you like.
- **Tidy up**: *Fast* (instant), *Automatic* (recommended) or *Best*. Speak checks what your computer can handle and tells you how quick each one will be. Rather keep every word, even "no wait"? Turn off *Fix changes of mind*.
- **The indicator**: near your cursor, or at the top or bottom of the screen, with one sliding line of live text, the full text, or none.
- **Light or dark**, or follow your system.
- **History** stays off unless you turn it on, and is only ever kept on your device.

## Support Speak

Speak is free, with no ads, no account and no paid tier. If it saves you time, the best way to keep it going and growing is to **sponsor it on GitHub**. GitHub takes no fee, and it can be monthly or one-off.

<p>
  <a href="https://github.com/sponsors/jacobjmarks"><img src="https://img.shields.io/badge/Sponsor_on_GitHub-EA4AAA?style=for-the-badge&logo=githubsponsors&logoColor=white" alt="Sponsor on GitHub"></a>
</p>

No GitHub account? You can also <a href="https://buymeacoffee.com/jacobjmarks">buy me a coffee</a> ☕ with a card. Not able to chip in? A star on GitHub or telling a friend helps too.

## Questions

**Does Speak send my voice anywhere?** No. Audio stays in memory on your computer and is discarded after each dictation. The only internet use is the one-time model download and an optional check for new versions.

**Do I need a powerful computer?** No. Speak runs on ordinary laptops. With a graphics card it can use a larger model for smarter tidying at the same speed.

**Which languages?** Speak detects the language you speak, or you can choose one in Settings → Advanced.

---

<p align="center"><sub>Built on open models: NVIDIA Nemotron speech recognition and Qwen for tidying up. Open-source notices are on the app's About page. Developers: see <a href="docs/DEVELOPMENT.md">docs/DEVELOPMENT.md</a>.</sub></p>
