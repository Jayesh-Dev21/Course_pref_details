(async () => {
    const BASE = "https://academicservices.iitbhu.ac.in";

    function sleep(ms) {
        return new Promise(r => setTimeout(r, ms));
    }

    function similarity(a, b) {
        a = a.toLowerCase();
        b = b.toLowerCase();

        const dp = Array(a.length + 1)
            .fill(0)
            .map(() => Array(b.length + 1).fill(0));

        for (let i = 0; i <= a.length; i++) dp[i][0] = i;
        for (let j = 0; j <= b.length; j++) dp[0][j] = j;

        for (let i = 1; i <= a.length; i++) {
            for (let j = 1; j <= b.length; j++) {
                const cost = a[i - 1] === b[j - 1] ? 0 : 1;

                dp[i][j] = Math.min(
                    dp[i - 1][j] + 1,
                    dp[i][j - 1] + 1,
                    dp[i - 1][j - 1] + cost
                );
            }
        }

        const dist = dp[a.length][b.length];
        return 1 - dist / Math.max(a.length, b.length);
    }

    async function getCSRF() {
        const html = await fetch(`${BASE}/studnt_acad/subj_search`).then(r => r.text());

        const doc = new DOMParser().parseFromString(html, "text/html");

        return doc.querySelector("input[name=csrfmiddlewaretoken]").value;
    }

    async function getOECourses() {
        const html = await fetch(`${BASE}/studnt_acad/subj_chcs/OE`).then(r => r.text());

        const doc = new DOMParser().parseFromString(html, "text/html");

        const courses = {};

        doc.querySelectorAll("li[data-code]").forEach(li => {
            const text = li.querySelector("span").textContent.trim();

            const rest = text.split(".", 2)[1];
            const parts = rest.split(":");

            const code = parts.shift().trim();
            const name = parts.join(":").trim();

            courses[code] = name;
        });

        return courses;
    }

    async function searchCourse(code) {
        const csrf = await getCSRF();

        const body = new URLSearchParams({
            csrfmiddlewaretoken: csrf,
            search: code,
            year_sem: "All",
            dept: "All"
        });

        const html = await fetch(`${BASE}/studnt_acad/subj_search`, {
            method: "POST",
            headers: {
                "Content-Type": "application/x-www-form-urlencoded",
            },
            body
        }).then(r => r.text());

        return html;
    }

    function chooseSubject(rows, oeName) {
        let exact = rows.find(
            r => r.name.toLowerCase() === oeName.toLowerCase()
        );

        if (exact) return exact;

        let best = rows[0];
        let score = 0;

        for (const row of rows) {
            const s = similarity(row.name, oeName);
            if (s > score) {
                score = s;
                best = row;
            }
        }

        if (score < 0.85) {
            console.warn(`Poor match "${oeName}" -> "${best.name}"`);
        }

        return best;
    }

    function parseCourse(html, oeName) {

        const doc = new DOMParser().parseFromString(html, "text/html");

        const tables = doc.querySelectorAll("table");

        if (tables.length < 2)
            throw new Error("Unexpected page layout");

        const infoRows = [];

        tables[0].querySelectorAll("tbody tr").forEach(tr => {

            const td = [...tr.querySelectorAll("td")].map(
                x => x.textContent.trim()
            );

            infoRows.push({
                code: td[0],
                name: td[1],
                credits: td[2],
                ltp: td[3],
                department: td[4],
                professor: td[5]
            });

        });

        const subject = chooseSubject(infoRows, oeName);

        const batches = [];

        tables[1].querySelectorAll("tbody tr").forEach(tr => {

            const td = [...tr.querySelectorAll("td")].map(
                x => x.textContent.trim()
            );

            batches.push({
                subject: td[0],
                type: td[1],
                credits: td[2],
                semester: td[3],
                batch: td[4]
            });

        });

        subject.batches = batches;

        return subject;
    }

    const db = {};

    const oe = await getOECourses();

    console.log(`Found ${Object.keys(oe).length} OE courses`);

    for (const [code, name] of Object.entries(oe)) {

        console.log("Downloading", code);

        try {
            const html = await searchCourse(code);

            db[code] = parseCourse(html, name);

        } catch (e) {
            console.error(code, e);
        }

        await sleep(300);
    }

    console.log("Done.");

    console.log(db);

    console.log(JSON.stringify(db, null, 2));

    try {
        await navigator.clipboard.writeText(JSON.stringify(db, null, 2));
        console.log("✅ JSON copied to clipboard.");
    } catch (e) {
        console.log("Clipboard permission denied.");
    }
})();
