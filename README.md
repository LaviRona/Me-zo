# ✨ Me Zo?

> *Small picture, big deal.*

Ever spent way too long trying to choose the perfect LinkedIn profile picture, only to find out it looks completely ruined once it's cropped into that tiny circular frame? 🤦‍♀️

Me-zo is a lightweight, interactive web app that lets you preview and compare multiple profile options at once — with zero ads and zero hassle. Just upload a couple of photos and start rolling! Your photos aren't saved anywhere — close the tab and they're gone.

## 🌐 Live Demo
Play with the live app here: 👉 **[https://mezomezo.streamlit.app/](https://mezomezo.streamlit.app/)**

## ✨ Features
- **Interactive Circle Cropper:** Drag to pan, scroll to zoom, and frame each face exactly the way LinkedIn will show it. The filmstrip on either side previews the rest of your queue with their saved crops.
- **Social Mockup Simulator:** Once you shortlist a photo to your lineup, watch it come to life instantly inside a hyper-realistic **LinkedIn Profile Card** and **Newsfeed Post** template (including comment layouts) to see exactly how it scales.
- **Smart Queue Management:** Pinned photos exit the active queue automatically, and an **Undo button** protects you from accidental discards.
- **Privacy-First:** Your photos aren't saved anywhere — close the tab and they're gone.

## 💡 The "Vibe Coding" Story
This entire application was engineered through **AI-assisted rapid prototyping (Vibe Coding)** using Claude Code. By shifting the role from simple syntax writing to system architecture and exact UX alignment, this production-ready application went from an annoying personal problem to a deployed tool in a few hours.

## 🛠 Tech Stack
- **Streamlit** — UI, session state, and hosting
- **Pillow (PIL)** — image cropping, EXIF orientation, and circular masking
- **Vanilla HTML / CSS / JavaScript** inside Streamlit iframes for the interactive cropper, side filmstrip, and LinkedIn mockups
- **Python 3.9+**

## 💻 How to Run Locally

1. **Install requirements:**
   ```bash
   pip install -r requirements.txt
   ```
2. **Run the app:**
   ```bash
   python -m streamlit run Me_zo.py
   ```
