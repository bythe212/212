// 데이터 계층: CSV/배열을 Dataset 으로 만들고 컬럼 단위로 조회한다.
(function (root) {
  const Sonify = root.Sonify;
  const { extent } = Sonify.util;

  // 따옴표("a, b"), 이스케이프된 따옴표(""), CRLF 를 처리하는 작은 CSV 파서.
  function parseCSVText(text, delimiter = ',') {
    const rows = [];
    let row = [];
    let field = '';
    let inQuotes = false;

    for (let i = 0; i < text.length; i++) {
      const c = text[i];
      if (inQuotes) {
        if (c === '"' && text[i + 1] === '"') {
          field += '"';
          i++;
        } else if (c === '"') {
          inQuotes = false;
        } else {
          field += c;
        }
      } else if (c === '"') {
        inQuotes = true;
      } else if (c === delimiter) {
        row.push(field);
        field = '';
      } else if (c === '\n' || c === '\r') {
        if (c === '\r' && text[i + 1] === '\n') i++;
        row.push(field);
        rows.push(row);
        row = [];
        field = '';
      } else {
        field += c;
      }
    }
    if (field !== '' || row.length > 0) {
      row.push(field);
      rows.push(row);
    }
    // 완전히 빈 줄은 버린다.
    return rows.filter((r) => r.some((f) => f.trim() !== ''));
  }

  // 숫자처럼 생긴 문자열은 숫자로, 빈 칸은 null(결측치)로 바꾼다.
  function autoType(value) {
    const s = value.trim();
    if (s === '') return null;
    const n = Number(s);
    return Number.isFinite(n) ? n : s;
  }

  class Dataset {
    constructor(rows, columns) {
      this.rows = rows;
      this.columns = columns || (rows.length ? Object.keys(rows[0]) : []);
      this._extents = {};
    }

    // [{year: 2020, value: 3}, ...] 형태의 배열에서 만든다.
    static fromRows(rows) {
      return new Dataset(rows.slice());
    }

    static fromCSV(text, { delimiter = ',', typed = true } = {}) {
      const [header, ...body] = parseCSVText(text, delimiter);
      if (!header) return new Dataset([], []);
      const columns = header.map((h) => h.trim());
      const rows = body.map((cells) => {
        const row = {};
        columns.forEach((name, j) => {
          const raw = cells[j] === undefined ? '' : cells[j];
          row[name] = typed ? autoType(raw) : raw;
        });
        return row;
      });
      return new Dataset(rows, columns);
    }

    get length() {
      return this.rows.length;
    }

    row(i) {
      return this.rows[i];
    }

    column(name) {
      return this.rows.map((r) => r[name]);
    }

    // 컬럼의 [min, max] (캐시됨).
    extent(name) {
      if (!this._extents[name]) this._extents[name] = extent(this.column(name));
      return this._extents[name];
    }
  }

  // 주의: fetch 는 file:// 에서 동작하지 않으므로 로컬 서버로 열어야 한다.
  async function loadCSV(url, options) {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`CSV 로드 실패: ${url} (${res.status})`);
    return Dataset.fromCSV(await res.text(), options);
  }

  Sonify.Dataset = Dataset;
  Sonify.parseCSVText = parseCSVText;
  Sonify.loadCSV = loadCSV;
})(globalThis);
