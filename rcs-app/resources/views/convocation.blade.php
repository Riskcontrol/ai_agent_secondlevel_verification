<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Risk Control Services Nigeria — Convocation Extractor</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    @vite(['resources/css/app.css','resources/js/convocation.js'])
</head>
<body class="bg-green-50 text-gray-900 font-sans">
    <header class="bg-gradient-to-r from-lime-500 to-lime-300 text-[#0a2912] border-b-4 border-lime-600">
        <div class="max-w-5xl mx-auto px-4 py-4">
            <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-full bg-[#0a2912] text-white flex items-center justify-center font-bold">RC</div>
                <div>
                    <h1 class="m-0 text-lg font-semibold">Risk Control Services Nigeria</h1>
                    <p class="m-0 text-xs opacity-90">Convocation PDF Extraction Console</p>
                </div>
            </div>
        </div>
    </header>

    <main class="max-w-5xl mx-auto px-4 py-6">
        <section class="bg-white border border-gray-200 rounded-xl p-4 shadow-sm mb-6">
            <h2 class="text-xl font-semibold mb-4">Upload Convocation PDF</h2>
            <form id="uploadForm" class="space-y-3">
                <div class="flex flex-col gap-2">
                    <label for="file" class="font-medium">PDF File</label>
                    <input id="file" name="file" type="file" accept="application/pdf" required class="rounded-lg border border-gray-300 px-3 py-2 outline-none focus:border-lime-500" />
                </div>
                <div class="flex flex-col gap-2">
                    <label for="session" class="font-medium">Session (optional)</label>
                    <input id="session" name="session" type="text" placeholder="e.g. 2021/2022" class="rounded-lg border border-gray-300 px-3 py-2 outline-none focus:border-lime-500" />
                </div>
                <button class="inline-flex items-center gap-2 rounded-lg bg-lime-500 text-[#0a2912] font-semibold px-4 py-2" type="submit">Upload & Process</button>
            </form>
            <div id="uploadMsg" class="text-sm text-gray-600 mt-2"></div>
        </section>

        <section class="bg-white border border-gray-200 rounded-xl p-4 shadow-sm mb-6">
            <div class="flex items-center justify-between mb-3">
                <h2 class="text-xl font-semibold">Documents</h2>
                <button id="deleteAllBtn" class="rounded-lg bg-red-600 text-white font-semibold px-4 py-2">Delete All PDFs & Data</button>
            </div>
            <div class="overflow-auto">
                <table class="w-full text-sm border-collapse" id="docsTable">
                    <thead>
                        <tr class="bg-gray-50 text-gray-900">
                            <th class="text-left p-2 border-b">ID</th>
                            <th class="text-left p-2 border-b">Filename</th>
                            <th class="text-left p-2 border-b">Session</th>
                            <th class="text-left p-2 border-b">Status</th>
                            <th class="text-left p-2 border-b">CSV</th>
                            <th class="text-left p-2 border-b">XLSX</th>
                            <th class="text-left p-2 border-b">DOCX</th>
                            <th class="text-left p-2 border-b">Created</th>
                        </tr>
                    </thead>
                    <tbody></tbody>
                </table>
            </div>
        </section>

        <section class="bg-white border border-gray-200 rounded-xl p-4 shadow-sm">
            <h2 class="text-xl font-semibold mb-3">Search Students</h2>
            <form id="searchForm" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-2 mb-3">
                <input type="text" id="q" placeholder="Name, course, faculty..." class="rounded-lg border border-gray-300 px-3 py-2 outline-none focus:border-lime-500" />
                <input type="text" id="faculty" placeholder="Faculty" class="rounded-lg border border-gray-300 px-3 py-2 outline-none focus:border-lime-500" />
                <input type="text" id="grade" placeholder="Grade (e.g. FIRST CLASS)" class="rounded-lg border border-gray-300 px-3 py-2 outline-none focus:border-lime-500" />
                <input type="text" id="sess" placeholder="Session (e.g. 2021/2022)" class="rounded-lg border border-gray-300 px-3 py-2 outline-none focus:border-lime-500" />
                <button class="inline-flex items-center gap-2 rounded-lg bg-lime-500 text-[#0a2912] font-semibold px-4 py-2 md:col-span-2 lg:col-span-1" type="submit">Search</button>
            </form>
            <div class="overflow-auto">
                <table class="w-full text-sm border-collapse" id="resultsTable">
                    <thead>
                        <tr class="bg-gray-50 text-gray-900">
                            <th class="text-left p-2 border-b">Surname</th>
                            <th class="text-left p-2 border-b">First Name</th>
                            <th class="text-left p-2 border-b">Other Name</th>
                            <th class="text-left p-2 border-b">Course</th>
                            <th class="text-left p-2 border-b">Faculty</th>
                            <th class="text-left p-2 border-b">Grade</th>
                            <th class="text-left p-2 border-b">Qualification</th>
                            <th class="text-left p-2 border-b">Session</th>
                        </tr>
                    </thead>
                    <tbody></tbody>
                </table>
            </div>
            <div id="searchMsg" class="text-sm text-gray-600 mt-2"></div>
        </section>
    </main>

    <footer class="text-center text-green-900 py-6">
        <div class="max-w-5xl mx-auto px-4">
            <small>© <span id="year"></span> Risk Control Services Nigeria</small>
        </div>
    </footer>
</body>
</html>
