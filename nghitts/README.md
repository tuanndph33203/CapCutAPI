# NGHI-TTS

A browser-based Text-to-Speech and Speech Recognition application powered by Piper TTS, Sherpa-ONNX, and ONNX Runtime Web. Generate high-quality speech and transcribe audio directly in your browser without requiring a server for inference. Supports **Vietnamese** (home page), **other languages** (English, Indonesian), and **ASR** (Automatic Speech Recognition) on separate pages. Live demo: https://nghitts.app.

## Features

### TTS (Text-to-Speech)

- 🌐 **Browser-Based TTS**: Fully client-side text-to-speech processing using Web Workers
- 🌍 **Multi-Language Pages**: Vietnamese (default), English (`/en`), and Indonesian (`/id`) each have their own page—switch via the tab bar.
- 🇻🇳 **Vietnamese Language Support**: Advanced Vietnamese text processing with automatic conversion of:
  - Numbers to words (0 to billions)
  - Dates and date ranges
  - Time expressions
  - Currency (VND, USD)
  - Percentages and decimals
  - Phone numbers
  - Ordinals
  - Roman numerals (I–XXX)
  - Numeric ranges with units and currency (e.g., "1-10m", "1/10kg")
- 🎤 **Multi-Speaker Models**: Support for models with multiple voices
- ⚡ **Real-Time Streaming**: Stream audio chunks as they're generated
- 🎚️ **Speed Control**: Adjustable speech speed
- 📥 **Audio Download**: Export generated audio as WAV files
- 🌙 **Dark Mode**: Built-in theme toggle
- 📊 **Text Statistics**: Character and word count display
- 🔄 **Dynamic Model Loading**: Load models on-demand from Cloudflare R2 storage
- 📜 **Generation History**: Automatically saves TTS results to IndexedDB—replay, download, or copy past generations from a slide-out history panel
- 🔗 **Share Button**: Copy the current page URL to clipboard for easy sharing

### ASR (Automatic Speech Recognition)

- 🎙️ **Browser-Based ASR**: Client-side speech recognition using Sherpa-ONNX WASM
- 🎤 **Microphone Mode**: Real-time recording with Voice Activity Detection (VAD)
- 📂 **File Upload Mode**: Transcribe any audio file with progress tracking
- 📝 **SRT Subtitle Export**: Download transcription as SRT subtitles with timestamps
- 🔁 **Multiple Model Support**: Switch between ASR models (SenseVoice, Whisper, Transducer, Paraformer, etc.)
- 💾 **Model Persistence**: Selected ASR model is saved in localStorage

## 🧠 Model Training Details

This project is built on top of Piper TTS and fine-tuned using a custom dataset to generate realistic voices.
Please see the Training Video here: https://www.youtube.com/watch?v=WgvBOljtNvE



### 🔹 Base Model

- **Based on Piper (English checkpoint)**
- Lightweight, fast, and optimized for local inference
- Designed for real-time speech generation

### 🔹 Fine-Tuning Process

**Dataset:**
- Dataset size: ~1,000 audio samples
- Voices: Multiple famous celebrity voices
- Training method: Fine-tuning on existing Piper English checkpoint
- Epochs: ~2,000 epochs
- **Download training datasets**: [View Datasets on Google Drive](https://drive.google.com/drive/folders/1NwVRepCQ4HgOfTn4BR9pbYJOF2KkvG4h?usp=sharing)

Available datasets include:
- Vietnamese celebrity voices (Mỹ Tâm, Ngọc Ngân, Trấn Thành, Việt Thảo)
- Multi-speaker datasets
- Various dataset sizes (200, 1000+ samples)
- English voice datasets

**Audio Preparation:**
- Cleaned and normalized audio
- Matched text–audio pairs
- Consistent sample rate
- Noise removed

**What the Model Learns:**
- Voice tone
- Accent
- Speech rhythm
- Natural pronunciation

### ⚡ Inference Method

- **Web-based inference**: No server required
- **Runs fully locally**: All processing happens in your browser
- **Very fast inference**: ~5× real-time speed
- **User-friendly**: Simply enter text, select a voice, and generate speech instantly

### ✅ Key Benefits

- ✔ Based on Piper TTS
- ✔ Fine-tuned with 1,000+ audio samples
- ✔ Trained for ~2,000 epochs
- ✔ No server required
- ✔ Web-based & lightweight
- ✔ Fast inference (≈5× real-time)
- ✔ Free & open-source
- ✔ Allowed for commercial use
- ✔ Easy to deploy or modify

## 📦 Available Models

Pre-trained Vietnamese TTS models are available for download:

**Download from Google Drive**: [View Available Models](https://drive.google.com/drive/folders/1f_pCpvgqfvO4fdNKM7WS4zTuXC0HBskL?usp=drive_link)

### Model List

1. **calmwoman3688** (~60.6 MB)
   - Files: `calmwoman3688.onnx` + `calmwoman3688.onnx.json`
   - Description: Female voice

2. **deepman3909** (~60.6 MB)
   - Files: `deepman3909.onnx` + `deepman3909.onnx.json`
   - Description: Male voice

3. **ngocngan3701** (~60.6 MB)
   - Files: `ngocngan3701.onnx` + `ngocngan3701.onnx.json`
   - Description: Vietnamese celebrity voice (Ngọc Ngân)

4. **vietthao3886** (~60.6 MB)
   - Files: `vietthao3886.onnx` + `vietthao3886.onnx.json`
   - Description: Vietnamese celebrity voice (Việt Thảo)
     
5. **New Voices**: Mỹ Tâm, Trấn Thành, Ngọc Huyền (review phim), Oryx (giọng nam siêu trầm)

### Model File Structure

Each TTS model requires **two files** with the same base name:
- `{model-name}.onnx` - The ONNX model file (binary)
- `{model-name}.onnx.json` - The model configuration file (JSON)

**For local development**, place models in the appropriate folders under `public/`:

```
public/
├── tts-model/
│   ├── vi/                    # Vietnamese TTS (home page /)
│   │   ├── calmwoman3688.onnx
│   │   ├── calmwoman3688.onnx.json
│   │   └── ...
│   ├── en/                    # English TTS (/en)
│   │   ├── en_US-libritts_r-medium.onnx
│   │   ├── en_US-libritts_r-medium.onnx.json
│   │   └── ...
│   └── id/                    # Indonesian TTS (/id)
│       └── ...
├── asr-model/                 # ASR models (/asr)
│   └── {model-name}/
│       └── ...                # Model-specific files
└── vad-model/silero-vad/      # VAD model (included)
    └── silero_vad.onnx
```

The dev server lists and serves TTS models from `tts-model/{lang}/` and ASR models from `asr-model/` when you run `npm run dev`.

## Using Other Languages (English, Indonesian)

1. **Open the language page**: Use the tab bar **Tiếng Việt** | **English** | **Indonesia** (or go to `/en` or `/id`).
2. **Add models locally**: Put `.onnx` and `.onnx.json` pairs in `public/tts-model/en/` for English or `public/tts-model/id/` for Indonesian.
3. **Select a model**: Choose a model from the dropdown (the app auto-selects a default model if none is chosen), then pick a voice (if the model has multiple speakers), enter text, and click Generate/Play.
4. **Production (Cloudflare R2)**: Upload English models under the `piper/en/` prefix and Indonesian under `piper/id/` in your R2 bucket; the app will list and serve them via `/api/piper/{lang}/models` and `/api/model/piper/{lang}/{name}`.

## Using ASR (Speech Recognition)

1. **Open the ASR page**: Click the **Nhận dạng giọng nói** tab in the tab bar (or go to `/asr`).
2. **Select an ASR model**: Choose from the model dropdown. The selected model is persisted in localStorage.
3. **Microphone mode**: Click the mic button to start real-time recording with VAD. Speech segments are automatically detected and transcribed.
4. **File upload mode**: Switch to the Upload tab and select an audio file. The file is decoded, segmented, and transcribed with timestamps.
5. **Export**: Download the transcription as plain text or SRT subtitles.
6. **Add ASR models locally**: Place model directories in `public/asr-model/` for local development.
7. **Production (Cloudflare R2)**: Upload ASR models under the `asr/` prefix in your R2 bucket; discovered via `/api/asr/models` and served via `/api/model/asr/{model}/{name}`.

## Tech Stack

- **Frontend**: Vue 3 + Vite
- **TTS Engine**: Piper TTS (ONNX format)
- **ASR Engine**: Sherpa-ONNX (WASM) with Silero VAD
- **Runtime**: ONNX Runtime Web (WASM)
- **Hosting**: Cloudflare Pages
- **Storage**: Cloudflare R2 (for TTS and ASR model files)
- **Styling**: Tailwind CSS
- **Icons**: Lucide Vue Next

## Project Structure

```
piper-tts-web-demo/
├── src/
│   ├── App.vue                 # Shell with tab bar (TTS + ASR), share/history buttons
│   ├── router/index.js         # Routes: / (Vietnamese), /en, /id, /asr
│   ├── views/
│   │   ├── VietnameseView.vue  # Vietnamese TTS page
│   │   ├── LanguageView.vue    # English/Indonesian TTS page (reusable)
│   │   └── ASRView.vue         # Speech recognition page (mic + file upload)
│   ├── components/
│   │   ├── HistoryPanel.vue    # Slide-out sidebar for TTS generation history
│   │   └── ...                 # AudioChunk, ModelSelector, SpeedControl, etc.
│   ├── lib/
│   │   ├── piper-tts.js        # Piper TTS (Vietnamese preprocessing)
│   │   └── piper-tts-i18n.js   # Piper TTS for /en and /id (no Vietnamese pipeline)
│   ├── utils/
│   │   ├── history-store.js    # IndexedDB-backed TTS history (max 50 entries)
│   │   ├── text-cleaner.js     # Text normalization and transliteration
│   │   ├── vietnamese-processor.js  # Vietnamese number/date/currency/Roman numeral conversion
│   │   └── ...                 # model-cache, model-detector, etc.
│   ├── workers/
│   │   ├── tts-worker.js       # Worker for Vietnamese page
│   │   └── tts-worker-i18n.js  # Worker for English/Indonesian pages
│   └── config.js               # TTS and ASR model URLs, defaults, and configuration
├── functions/api/
│   ├── models.ts               # List Vietnamese TTS models (R2 prefix piper/vi/)
│   ├── model/[name].ts         # Serve Vietnamese TTS model files
│   ├── piper/[lang]/models.ts  # List TTS models for a language
│   ├── model/piper/[lang]/[name].ts  # Serve TTS model for a language
│   ├── asr/models.ts           # List ASR models (R2 prefix asr/)
│   └── model/asr/[model]/[name].ts   # Serve ASR model files
└── public/
    ├── favicon.png              # Site favicon
    ├── tts-model/vi/            # Vietnamese TTS models (local)
    ├── tts-model/en/            # English TTS models (local)
    ├── tts-model/id/            # Indonesian TTS models (local)
    ├── asr-model/               # ASR models (local, for dev)
    ├── code/asr-wasm/           # Sherpa-ONNX WASM scripts (ASR + VAD)
    ├── vad-model/silero-vad/    # Silero VAD model (silero_vad.onnx)
    ├── non-vietnamese-words.csv
    └── acronyms.csv
```

## How It Works

### TTS Pipeline

1. **Model Loading**: TTS models are stored in Cloudflare R2 and served via Cloudflare Pages Functions
2. **Text Processing**: Vietnamese text is processed to convert numbers, dates, times, Roman numerals, ranges, etc. to spoken words
3. **Text Chunking**: Input text is intelligently split into chunks for optimal processing
4. **Phoneme Conversion**: Text is converted to phonemes using the phonemizer library
5. **Audio Generation**: ONNX Runtime Web runs the Piper TTS model in a Web Worker
6. **Streaming**: Audio chunks are streamed back to the main thread and played as they're generated
7. **Audio Merging**: Chunks are merged, normalized, and trimmed for final output
8. **History**: Generated audio is automatically saved to IndexedDB for later replay or download

### ASR Pipeline

1. **Model Loading**: ASR models are loaded from Cloudflare R2 (or local `public/asr-model/` in dev)
2. **WASM Initialization**: Sherpa-ONNX WASM module is loaded with the selected ASR model
3. **Microphone Mode**: Audio is captured from the microphone, processed through Silero VAD for voice activity detection, and fed to the offline recognizer
4. **File Upload Mode**: Audio files are decoded, segmented by VAD, and transcribed with timestamps
5. **Output**: Transcription text is displayed and can be downloaded as plain text or SRT subtitles

## Vietnamese Text Processing

The application includes comprehensive Vietnamese text processing that handles:

- **Numbers**: Automatic conversion to Vietnamese words (e.g., "123" → "một trăm hai mươi ba")
- **Dates**: Multiple formats (DD/MM/YYYY, DD-MM-YYYY, date ranges)
- **Times**: Time expressions (HH:MM, HH:MM:SS, "X giờ Y phút")
- **Currency**: VND (đồng) and USD conversion
- **Percentages**: Automatic conversion (e.g., "50%" → "năm mươi phần trăm")
- **Decimals**: Vietnamese decimal format (comma as decimal separator)
- **Phone Numbers**: Digit-by-digit reading
- **Ordinals**: Conversion of ordinal numbers (thứ 2 → thứ hai)
- **Roman Numerals**: Conversion of I–XXX to Arabic digits (configurable via `UnlimitedRomanNumerals` in `config.json`)
- **Ranges with Units/Currency**: Numeric ranges and fractions with units (e.g., "1-10m" → "1 đến 10 m", "1/10kg" → "1 phần 10 kg")

## Running Locally

### Prerequisites

- Node.js 18+ 
- npm or yarn

### Step 1: Install Dependencies

```bash
npm install
npm install phonemizer-1.2.2.tgz
```

### Step 2: Download Models

1. **Download models from Google Drive**: [View Available Models](https://drive.google.com/drive/folders/1f_pCpvgqfvO4fdNKM7WS4zTuXC0HBskL?usp=drive_link)

2. **Create the models directory** (if it doesn't exist):
   ```bash
   mkdir -p public/tts-model/vi
   ```

3. **Place Vietnamese model files in `public/tts-model/vi/`**:
   - Each model requires **two files**:
     - `{model-name}.onnx` - The ONNX model file (~60-80 MB)
     - `{model-name}.onnx.json` - The model configuration file
   - Example: For the `calmwoman3688` model, you need:
     - `public/tts-model/vi/calmwoman3688.onnx`
     - `public/tts-model/vi/calmwoman3688.onnx.json`

4. **Recommended models to start with** (in `public/tts-model/vi/`):
   - `calmwoman3688` - Female voice
   - `deepman3909` - Male voice
   - `ngocngan3701` - Vietnamese celebrity voice
   - `vietthao3886` - Vietnamese celebrity voice

   **Note**: The app detects all models in `public/tts-model/vi/`. For **English** or **Indonesian**, put models in `public/tts-model/en/` or `public/tts-model/id/` and use the tab bar to switch pages.

5. **(Optional) ASR models**: Place ASR model directories in `public/asr-model/` for speech recognition:
   ```
   public/asr-model/{model-name}/
   ```
   The VAD model (`silero_vad.onnx`) is already included in `public/vad-model/silero-vad/`.

### Step 3: Start Development Server

```bash
npm run dev
```

The application will be available at `http://localhost:5173` (or the port shown in the terminal).

The development server automatically:
- Serves **Vietnamese** TTS models from `public/tts-model/vi/` (list: `/api/models`, files: `/api/model/{name}`)
- Serves **English/Indonesian** TTS models from `public/tts-model/en/` and `public/tts-model/id/` (list: `/api/piper/{lang}/models`, files: `/api/model/piper/{lang}/{name}`)
- Serves **ASR** models from `public/asr-model/` (list: `/api/asr/models`, files: `/api/model/asr/{model}/{name}`)

### Step 4: Use the Application

1. Open your browser and navigate to the development server URL.
2. **Vietnamese (home)**: Use the **Tiếng Việt** tab or `/`. Select a model from the dropdown (from `public/tts-model/vi/`), enter text, then Generate/Play.
3. **English or Indonesian**: Click **English** or **Indonesia** in the tab bar (or go to `/en` or `/id`). Add models to `public/tts-model/en/` or `public/tts-model/id/`, then select a model, choose a voice if available, enter text, and Generate/Play.
4. **ASR**: Click **Nhận dạng giọng nói** in the tab bar (or go to `/asr`). Select an ASR model, then use the mic or upload an audio file for transcription.

## Development

### Build for Production

```bash
npm run build
```

The production build will be in the `dist/` folder.

### Preview Production Build

```bash
npm run preview
```

This serves the production build locally for testing.

## Deployment

The project is configured for Cloudflare Pages deployment:

1. **TTS models** should be stored in a Cloudflare R2 bucket (e.g. `tts-bucket`) with **language prefixes**:
   - **Vietnamese**: `piper/vi/{model-name}.onnx` and `piper/vi/{model-name}.onnx.json` (discovered via `/api/models`)
   - **English**: `piper/en/{model-name}.onnx` and `.onnx.json` (discovered via `/api/piper/en/models`)
   - **Indonesian**: `piper/id/{model-name}.onnx` and `.onnx.json` (discovered via `/api/piper/id/models`)
   - Each TTS model requires two files (`.onnx` + `.onnx.json`) per language folder.

2. **ASR models** should be stored under the `asr/` prefix in the same R2 bucket:
   - `asr/{model-name}/{file}` (discovered via `/api/asr/models`, served via `/api/model/asr/{model}/{name}`)
   - Model files are served with 1-year immutable cache headers.

The Cloudflare Pages Functions discover and serve models by prefix.

## Configuration

### Wrangler Configuration

The `wrangler.toml` file configures:
- Pages build output directory
- R2 bucket binding (`piper` → `tts-bucket`)

### Application Configuration

`src/config.json` controls runtime behavior:
- `debug` – Enable/disable debug logging
- `UnlimitedRomanNumerals` – When `false`, only Roman numerals I–XXX are converted; when `true`, all valid Roman numerals are converted

### TTS Model Format

TTS models must be in Piper TTS ONNX format with:
- `.onnx` file containing the ONNX model
- `.onnx.json` file containing voice configuration (phoneme_id_map, audio settings, etc.)

## Features in Detail

### Text Cleaning

- Removes emojis and special characters
- Normalizes Unicode (NFC)
- Handles Vietnamese-specific punctuation
- Cleans whitespace

### Text Chunking

- Intelligently splits text into optimal chunks
- Respects sentence boundaries
- Handles long sentences by splitting at word boundaries
- Maintains minimum and maximum chunk sizes for optimal processing

### Audio Processing

- Real-time streaming of audio chunks
- Automatic normalization and peak limiting
- Silence trimming
- Sample rate preservation

## Browser Compatibility

- Modern browsers with WebAssembly support
- Web Workers support required
- ES Modules support required

## 📜 License & Usage

This project is:

- ✅ **Free to use**
- ✅ **Open source**
- ✅ **Allowed for commercial use**
- ✅ **Customizable and deployable**

⚠️ **Important**: Users are responsible for complying with voice and content laws when using generated audio.

## Acknowledgments

- Built on [Piper TTS (GPL)](https://github.com/OHF-Voice/piper1-gpl) by OHF-Voice
- Inspired by [piper-tts-web-demo](https://clowerweb.github.io/piper-tts-web-demo/) by clowerweb
- Uses [ONNX Runtime Web](https://github.com/microsoft/onnxruntime) for browser-based TTS inference
- Uses [Sherpa-ONNX](https://github.com/k2-fsa/sherpa-onnx) for browser-based ASR with Silero VAD
