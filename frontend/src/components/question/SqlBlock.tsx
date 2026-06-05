const KEYWORDS = ['SELECT', 'FROM', 'WHERE', 'GROUP BY', 'HAVING', 'ORDER BY',
  'JOIN', 'LEFT JOIN', 'RIGHT JOIN', 'INNER JOIN', 'ON', 'AS', 'INSERT', 'UPDATE',
  'DELETE', 'CREATE', 'DROP', 'ALTER', 'TABLE', 'INTO', 'VALUES', 'SET', 'DISTINCT',
  'UNION', 'ALL', 'EXISTS', 'NOT', 'IN', 'BETWEEN', 'LIKE', 'AND', 'OR', 'IS', 'NULL',
];

const FUNCTIONS = ['AVG', 'COUNT', 'SUM', 'MAX', 'MIN', 'COALESCE', 'NVL',
  'DECODE', 'CASE', 'WHEN', 'THEN', 'ELSE', 'END', 'RANK', 'ROW_NUMBER', 'OVER',
];

function highlight(sql: string): string {
  let out = sql
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  KEYWORDS.forEach((kw) => {
    out = out.replace(new RegExp(`\\b(${kw})\\b`, 'gi'),
      (m) => `<span class="kw">${m}</span>`);
  });
  FUNCTIONS.forEach((fn) => {
    out = out.replace(new RegExp(`\\b(${fn})\\b`, 'gi'),
      (m) => `<span class="fn">${m}</span>`);
  });
  out = out.replace(/'([^']*)'/g, "<span class=\"str\">'$1'</span>");
  out = out.replace(/(--[^\n]*)/g, '<span class="com">$1</span>');

  return out;
}

export default function SqlBlock({ sql }: { sql: string }) {
  return (
    <div
      className="sql-block"
      dangerouslySetInnerHTML={{ __html: highlight(sql) }}
    />
  );
}
