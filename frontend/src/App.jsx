import { useEffect, useRef, useState } from 'react'
import './App.css'
import { generateNotes, getMeetings, uploadAudio } from './api'

function App() {
  const [isRecording, setIsRecording] = useState(false)
  const [audioBlob, setAudioBlob] = useState(null)
  const [audioUrl, setAudioUrl] = useState('')
  const [fileName, setFileName] = useState('')
  const [transcript, setTranscript] = useState('')
  const [notes, setNotes] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [meetings, setMeetings] = useState([])
  const [historyLoading, setHistoryLoading] = useState(false)

  const mediaRecorderRef = useRef(null)
  const chunksRef = useRef([])

  const formatActionItems = (items) => JSON.stringify(items || [], null, 2)

  const loadMeetings = async () => {
    setHistoryLoading(true)
    try {
      const history = await getMeetings()
      setMeetings(history)
    } catch (err) {
      setError(err.message || 'Failed to load history')
    } finally {
      setHistoryLoading(false)
    }
  }

  useEffect(() => {
    loadMeetings()
  }, [])

  const startRecording = async () => {
    setError('')
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    const recorder = new MediaRecorder(stream)
    chunksRef.current = []

    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) {
        chunksRef.current.push(event.data)
      }
    }

    recorder.onstop = () => {
      const blob = new Blob(chunksRef.current, { type: 'audio/webm' })
      const generatedUrl = URL.createObjectURL(blob)
      setAudioBlob(blob)
      setAudioUrl(generatedUrl)
      setFileName(`meeting-${Date.now()}.webm`)
      stream.getTracks().forEach((track) => track.stop())
    }

    mediaRecorderRef.current = recorder
    recorder.start()
    setIsRecording(true)
  }

  const stopRecording = () => {
    if (!mediaRecorderRef.current) return
    mediaRecorderRef.current.stop()
    setIsRecording(false)
  }

  const onFileChange = (event) => {
    const file = event.target.files?.[0]
    if (!file) return
    setAudioBlob(file)
    setAudioUrl(URL.createObjectURL(file))
    setFileName(file.name)
    setError('')
  }

  const handleGenerateNotes = async () => {
    if (!audioBlob) {
      setError('Please record or select an audio file first.')
      return
    }

    setLoading(true)
    setError('')
    try {
      const file = audioBlob instanceof File ? audioBlob : new File([audioBlob], fileName, { type: audioBlob.type })
      const upload = await uploadAudio(file)
      const generated = await generateNotes({ fileUrl: upload.file_url })
      setTranscript(generated.transcript)
      setNotes(generated.notes)
      await loadMeetings()
    } catch (err) {
      setError(err.message || 'An unexpected error occurred')
    } finally {
      setLoading(false)
    }
  }

  const exportJson = () => {
    if (!notes) return
    const payload = {
      transcript,
      notes,
      created_at: new Date().toISOString(),
    }
    const blob = new Blob([JSON.stringify(payload, null, 2)], {
      type: 'application/json',
    })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `meeting-minutes-${Date.now()}.json`
    anchor.click()
    URL.revokeObjectURL(url)
  }

  const updateNotesField = (field, value) => {
    setNotes((prev) => ({ ...prev, [field]: value }))
  }

  const selectMeeting = (meeting) => {
    setTranscript(meeting.transcript || '')
    setNotes(meeting.notes || null)
  }

  return (
    <main className="page">
      <section className="card">
        <h1>Meeting Minutes AI</h1>
        <p className="subtitle">Record a meeting, transcribe it, and generate professional notes.</p>

        <div className="controls">
          <button className={isRecording ? 'danger' : ''} onClick={isRecording ? stopRecording : startRecording}>
            {isRecording ? 'Stop Recording' : 'Start Recording'}
          </button>
          <label className="file-input">
            Upload Audio
            <input type="file" accept="audio/*" onChange={onFileChange} />
          </label>
          <button onClick={handleGenerateNotes} disabled={loading}>
            {loading ? 'Generating...' : 'Generate Notes'}
          </button>
        </div>

        {fileName && <p className="meta">Selected audio: {fileName}</p>}
        {audioUrl && <audio controls src={audioUrl} className="audio-player" />}
        {error && <p className="error">{error}</p>}
      </section>

      <section className="card">
        <div className="section-header">
          <h2>Meeting History</h2>
          <button onClick={loadMeetings} disabled={historyLoading}>
            {historyLoading ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>
        {!meetings.length && <p className="meta">No saved meetings yet.</p>}
        <div className="history-list">
          {meetings.map((meeting) => (
            <button key={meeting.id} className="history-item" onClick={() => selectMeeting(meeting)}>
              <strong>{meeting.notes?.title || `Meeting ${meeting.id}`}</strong>
              <span>{new Date(meeting.created_at).toLocaleString()}</span>
            </button>
          ))}
        </div>
      </section>

      <section className="card">
        <h2>Transcript</h2>
        <textarea
          value={transcript}
          onChange={(e) => setTranscript(e.target.value)}
          placeholder="Transcript appears here after generation."
          rows={8}
        />
      </section>

      <section className="card">
        <div className="section-header">
          <h2>Generated Notes</h2>
          <button onClick={exportJson} disabled={!notes}>
            Export JSON
          </button>
        </div>
        {!notes && <p className="meta">No notes generated yet.</p>}

        {notes && (
          <div className="notes-grid">
            <label>
              Title
              <input value={notes.title} onChange={(e) => updateNotesField('title', e.target.value)} />
            </label>
            <label>
              Summary
              <textarea value={notes.summary} onChange={(e) => updateNotesField('summary', e.target.value)} rows={4} />
            </label>
            <label>
              Key Points (one per line)
              <textarea
                value={(notes.key_points || []).join('\n')}
                onChange={(e) => updateNotesField('key_points', e.target.value.split('\n').filter(Boolean))}
                rows={6}
              />
            </label>
            <label>
              Decisions (one per line)
              <textarea
                value={(notes.decisions || []).join('\n')}
                onChange={(e) => updateNotesField('decisions', e.target.value.split('\n').filter(Boolean))}
                rows={6}
              />
            </label>
            <label>
              Action Items (JSON array)
              <textarea
                value={formatActionItems(notes.action_items)}
                onChange={(e) => {
                  try {
                    const parsed = JSON.parse(e.target.value)
                    if (Array.isArray(parsed)) {
                      updateNotesField('action_items', parsed)
                    }
                  } catch {
                    // Keep editing experience smooth; only update on valid JSON.
                  }
                }}
                rows={8}
              />
            </label>
          </div>
        )}
      </section>
    </main>
  )
}

export default App
