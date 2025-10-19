const API = {
  upload: '/api/upload',
  list: '/api/documents',
  delAll: '/api/documents',
  search: '/api/search'
}

function $(sel){ return document.querySelector(sel) }
function el(tag, attrs={}){ const e=document.createElement(tag); Object.assign(e, attrs); return e }

document.addEventListener('DOMContentLoaded', () => {
  const y = document.getElementById('year'); if (y) y.textContent = new Date().getFullYear();
  loadDocs()

  const up = $('#uploadForm');
  if (up) up.addEventListener('submit', async (e) => {
    e.preventDefault()
    const f = $('#file').files[0]
    if (!f) return
    const fd = new FormData()
    fd.append('file', f)
    if ($('#session')?.value) fd.append('session', $('#session').value)
    const sp = $('#start_page')?.value?.trim(); if (sp) fd.append('start_page', sp)
    const ep = $('#end_page')?.value?.trim(); if (ep) fd.append('end_page', ep)

    const msg = $('#uploadMsg'); if (msg) msg.textContent = 'Uploading...'
    try {
      const r = await fetch(API.upload, { method:'POST', body: fd })
      await r.json()
      if (msg) msg.textContent = 'Queued for processing. Refresh documents shortly.'
      loadDocs()
    } catch(err){
      if (msg) msg.textContent = 'Upload failed.'
    }
  })

  const del = $('#deleteAllBtn');
  if (del) del.addEventListener('click', async () => {
    if (!confirm('Delete ALL PDFs and extracted data?')) return
    await fetch(API.delAll, { method: 'DELETE' })
    loadDocs()
  })

  const sf = $('#searchForm');
  if (sf) sf.addEventListener('submit', async (e) => {
    e.preventDefault()
    const params = new URLSearchParams()
    const q = $('#q')?.value?.trim(); if(q) params.set('q', q)
    const faculty = $('#faculty')?.value?.trim(); if(faculty) params.set('faculty', faculty)
    const grade = $('#grade')?.value?.trim(); if(grade) params.set('grade', grade)
    const sess = $('#sess')?.value?.trim(); if(sess) params.set('session', sess)

    const msg = $('#searchMsg'); if (msg) msg.textContent = 'Searching...'
    try {
      const r = await fetch(API.search + '?' + params.toString())
      const j = await r.json()
      renderResults(j.data || [])
      if (msg) msg.textContent = `${(j.data||[]).length} results`
    } catch(err){
      if (msg) msg.textContent = 'Search failed.'
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
  const tbody = document.querySelector('#docsTable tbody')
  if (!tbody) return
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
      td(new Date(d.created_at).toLocaleString())
    )
    tbody.appendChild(tr)
  })
}

function renderResults(rows){
  const tbody = document.querySelector('#resultsTable tbody')
  if (!tbody) return
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

function td(v){ const d=document.createElement('td'); d.textContent=v??''; d.className='p-2 border-b'; return d }
function tdLink(url){
  const d=document.createElement('td'); d.className='p-2 border-b'
  if(url){ const a=document.createElement('a'); a.href=url; a.target='_blank'; a.className='text-lime-700 underline'; a.textContent='Download'; d.appendChild(a) }
  return d
}
