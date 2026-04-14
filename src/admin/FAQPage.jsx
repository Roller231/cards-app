import { useState, useEffect } from 'react'
import axios from 'axios'
import { API_BASE_URL } from '../api/client'
import Btn from '../components/ui/Btn'

function FAQPage() {
  const [faqs, setFaqs] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [editingFaq, setEditingFaq] = useState(null)
  const [newQuestion, setNewQuestion] = useState('')
  const [newAnswer, setNewAnswer] = useState('')
  const [createMode, setCreateMode] = useState(false)

  useEffect(() => {
    fetchFaqs()
  }, [])

  const fetchFaqs = async () => {
    try {
      setLoading(true)
      const response = await axios.get(`${API_BASE_URL}/faq/`)
      setFaqs(response.data.faqs || [])
      setLoading(false)
    } catch (err) {
      setError('Failed to load FAQs')
      setLoading(false)
      console.error(err)
    }
  }

  const startEditing = (faq) => {
    setEditingFaq(faq.id)
    setNewQuestion(faq.question)
    setNewAnswer(faq.answer)
  }

  const cancelEditing = () => {
    setEditingFaq(null)
    setNewQuestion('')
    setNewAnswer('')
    setCreateMode(false)
  }

  const saveFaq = async () => {
    if (!newQuestion || !newAnswer) return alert('Question and answer are required')
    try {
      if (createMode) {
        await axios.post(`${API_BASE_URL}/faq/`, { question: newQuestion, answer: newAnswer })
      } else {
        await axios.put(`${API_BASE_URL}/faq/${editingFaq}`, { question: newQuestion, answer: newAnswer })
      }
      await fetchFaqs()
      cancelEditing()
    } catch (err) {
      console.error(err)
      alert('Failed to save FAQ')
    }
  }

  const deleteFaq = async (id) => {
    if (!confirm('Are you sure you want to delete this FAQ?')) return
    try {
      await axios.delete(`${API_BASE_URL}/faq/${id}`)
      await fetchFaqs()
    } catch (err) {
      console.error(err)
      alert('Failed to delete FAQ')
    }
  }

  const startCreating = () => {
    setCreateMode(true)
    setNewQuestion('')
    setNewAnswer('')
    setEditingFaq(null)
  }

  if (loading) return <div style={{ padding: 32 }}>Loading...</div>
  if (error) return <div style={{ padding: 32, color: 'red' }}>{error}</div>

  return (
    <div style={{ maxWidth: 1000, margin: '0 auto' }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 24 }}>FAQ Management</h1>
      <div style={{ marginBottom: 24 }}>
        <Btn onClick={startCreating} style={{ background: '#4338ca', color: 'white' }}>+ Add New FAQ</Btn>
      </div>
      {(createMode || editingFaq) && (
        <div style={{ background: 'white', padding: 24, borderRadius: 12, marginBottom: 24, boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)' }}>
          <h2 style={{ fontSize: 18, marginBottom: 16 }}>{createMode ? 'Add New FAQ' : 'Edit FAQ'}</h2>
          <div style={{ marginBottom: 16 }}>
            <label style={{ display: 'block', marginBottom: 8, fontWeight: 500 }}>Question</label>
            <input
              type="text"
              value={newQuestion}
              onChange={(e) => setNewQuestion(e.target.value)}
              style={{ width: '100%', padding: 12, border: '1px solid #e5e7eb', borderRadius: 8, fontSize: 14 }}
              placeholder="Enter question"
            />
          </div>
          <div style={{ marginBottom: 16 }}>
            <label style={{ display: 'block', marginBottom: 8, fontWeight: 500 }}>Answer</label>
            <textarea
              value={newAnswer}
              onChange={(e) => setNewAnswer(e.target.value)}
              style={{ width: '100%', padding: 12, border: '1px solid #e5e7eb', borderRadius: 8, fontSize: 14, minHeight: 120, resize: 'vertical' }}
              placeholder="Enter answer"
            />
          </div>
          <div style={{ display: 'flex', gap: 12 }}>
            <Btn onClick={saveFaq} style={{ background: '#4338ca', color: 'white' }}>Save</Btn>
            <Btn onClick={cancelEditing} style={{ background: '#e5e7eb', color: '#1f2937' }}>Cancel</Btn>
          </div>
        </div>
      )}
      <div style={{ background: 'white', borderRadius: 12, overflow: 'hidden', boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)' }}>
        {faqs.length === 0 ? (
          <div style={{ padding: 32, textAlign: 'center', color: '#6b7280' }}>No FAQs found. Add a new FAQ to get started.</div>
        ) : (
          faqs.map(faq => (
            <div key={faq.id} style={{ borderBottom: faqs.indexOf(faq) !== faqs.length - 1 ? '1px solid #e5e7eb' : 'none', padding: '20px 24px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
                <div>
                  <div style={{ fontWeight: 600, fontSize: 16, color: '#111827' }}>{faq.question}</div>
                  <div style={{ fontSize: 14, color: '#6b7280', marginTop: 4, lineHeight: '1.5' }}>{faq.answer.substring(0, 150)}{faq.answer.length > 150 ? '...' : ''}</div>
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <Btn small onClick={() => startEditing(faq)} style={{ background: '#e5e7eb', color: '#1f2937', padding: '6px 12px' }}>Edit</Btn>
                  <Btn small onClick={() => deleteFaq(faq.id)} style={{ background: '#fee2e2', color: '#dc2626', padding: '6px 12px' }}>Delete</Btn>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

export default FAQPage
