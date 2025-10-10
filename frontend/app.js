const API = {
  upload: '/api/upload',
  list: '/api/documents',
  delAll: '/api/documents',
  search: '/api/search'
}

function $(sel){ return document.querySelector(sel) }
function el(tag, attrs={}){ const e=document.createElement(tag); Object.assign(e, attrs); return e }

document.addEventListener('DOMContentLoaded', () => {
  $('#year').textContent = new Date().getFullYear()
  loadDocs()

  $('#uploadForm').addEventListener('submit', async (e) => {
    e.preventDefault()
    const f = $('#file').files[0]
    if (!f) return
    const fd = new FormData()
    fd.append('file', f)
    if ($('#session').value) fd.append('session', $('#session').value)

    $('#uploadMsg').textContent = 'Uploading...'
    try {
      const r = await fetch(API.upload, { method:'POST', body: fd })
      const j = await r.json()
      $('#uploadMsg').textContent = 'Queued for processing. Refresh documents shortly.'
      loadDocs()
    } catch(err){
      $('#uploadMsg').textContent = 'Upload failed.'
    }
  })

  $('#deleteAllBtn').addEventListener('click', async () => {
    if (!confirm('Delete ALL PDFs and extracted data?')) return
    await fetch(API.delAll, { method: 'DELETE' })
    loadDocs()
  })

  $('#searchForm').addEventListener('submit', async (e) => {
    e.preventDefault()
    const params = new URLSearchParams()
    const q = $('#q').value.trim(); if(q) params.set('q', q)
    const faculty = $('#faculty').value.trim(); if(faculty) params.set('faculty', faculty)
    const grade = $('#grade').value.trim(); if(grade) params.set('grade', grade)
    const sess = $('#sess').value.trim(); if(sess) params.set('session', sess)

    $('#searchMsg').textContent = 'Searching...'
    try {
      const r = await fetch(API.search + '?' + params.toString())
      const j = await r.json()
      renderResults(j.data || [])
      $('#searchMsg').textContent = `${(j.data||[]).length} results`
    } catch(err){
      $('#searchMsg').textContent = 'Search failed.'
    }
  })
})

async function loadDocs(){
  try {
    const r = await fetch(API.list)
    const list = await r.json()
    renderDocs(list)
  } catch(err){
    // ignore
  }
}

function renderDocs(list){
  const tbody = $('#docsTable tbody')
  tbody.innerHTML = ''
  list.forEach(d => {
    const tr = el('tr')
    tr.append(
      td(d.id),
      td(d.filename),
      td(d.session||''),
      td(d.status),
      tdLink(d.csv_url),
      tdLink(d.xlsx_url),
      tdLink(d.docx_url),
      td(new Date(d.created_at).toLocaleString())
    )
    tbody.appendChild(tr)
  })
}

function renderResults(rows){
  const tbody = $('#resultsTable tbody')
  tbody.innerHTML = ''
  rows.forEach(r => {
    const tr = el('tr')
    tr.append(
      td(r.surname),
      td(r.first_name),
      td(r.other_name||''),
      td(r.course_studied||''),
      td(r.faculty||''),
      td(r.grade||''),
      td(r.qualification_obtained||''),
      td(r.session||'')
    )
    tbody.appendChild(tr)
  })
}

function td(v){ const d=el('td'); d.textContent=v??''; return d }
function tdLink(url){
  const d=el('td')
  if(url){ const a=el('a',{href:url, target:'_blank'}); a.textContent='Download'; d.appendChild(a) }
  return d
}
