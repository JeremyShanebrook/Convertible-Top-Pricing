/* Decode the catalog embedded in the bundled assets/index.html and verify:
 * - total row count == 19,450 (and per-supplier counts)
 * - 2006 Ford Mustang: rows from all 3 suppliers under the canonical model
 * - Miata Streamline: 2904C Stayfast $1,031.00, 5.5h
 * Uses the page's own documented row layout (columns comment in the file).
 */
const fs = require("fs");
const vm = require("vm");

const BUNDLED = "/home/hatch/workspace/projects/convertible-top-app/android/app/src/main/assets/index.html";
const html = fs.readFileSync(BUNDLED, "utf8");
let pass = 0, fail = 0;
function check(name, cond, extra) {
  if (cond) { pass++; console.log("PASS", name); }
  else { fail++; console.log("FAIL", name, extra || ""); }
}

// Extract + evaluate the window.CTP payload (first <script> block).
const start = html.indexOf("window.CTP = {");
const end = html.indexOf("</script>", start);
const sandbox = { window: {} };
vm.createContext(sandbox);
vm.runInContext(html.slice(start, end), sandbox);
const CTP = sandbox.window.CTP;
check("payload decoded (rows present)", Array.isArray(CTP.rows), typeof CTP.rows);

const SUPPLIERS = ["Robbins", "GAHH", "EZON"];
const D = CTP.dicts, COLORS = CTP.colors;
function ds(field, i) { return i == null ? null : D[field][i]; }
const ROWS = CTP.rows.map((r, idx) => ({
  id: idx + 1,
  supplier: SUPPLIERS[r[0]],
  yearStart: r[1], yearEnd: r[2],
  make: ds("make", r[3]), model: ds("model", r[4]),
  variantLabel: ds("variant_label", r[5]) || "",
  sku: r[6], coreNumber: r[7],
  priceMsrpCents: r[8], laborHours: r[9],
  material: ds("material", r[13]),
  styleLabel: ds("style_label", r[20]),
  isOriginalStyle: r[21] == null ? null : r[21] === 1,
}));

const counts = {};
ROWS.forEach((r) => { counts[r.supplier] = (counts[r.supplier] || 0) + 1; });
console.log("rows:", ROWS.length, JSON.stringify(counts));
check("total rows == 19450", ROWS.length === 19450, "got " + ROWS.length);
check("Robbins == 10648", counts.Robbins === 10648, "got " + counts.Robbins);
check("GAHH == 1886", counts.GAHH === 1886, "got " + counts.GAHH);
check("EZON == 6916", counts.EZON === 6916, "got " + counts.EZON);

// 2006 Ford Mustang: rows whose year range covers 2006, make Ford, model
// naming a Mustang — suppliers spell the model differently ("Mustang",
// "Mustang / Mustang GT", "Mustang, Cobra", ...), which the page's
// canonicalization aggregates under one "Mustang" model.
const mustang = ROWS.filter((r) =>
  r.make === "Ford" && /mustang/i.test(r.model || "") &&
  r.yearStart <= 2006 && (r.yearEnd == null || r.yearEnd >= 2006));
const mustangSuppliers = [...new Set(mustang.map((r) => r.supplier))].sort();
console.log("2006 Mustang rows:", mustang.length, "suppliers:", mustangSuppliers.join(", "));
mustangSuppliers.forEach((s) => {
  const ex = mustang.find((r) => r.supplier === s);
  console.log("  ", s, "e.g. sku", ex.sku, "core", ex.coreNumber, "years", ex.yearStart + "-" + ex.yearEnd);
});
check("2006 Mustang has all 3 suppliers", mustangSuppliers.length === 3 &&
  mustangSuppliers.includes("Robbins") && mustangSuppliers.includes("GAHH") &&
  mustangSuppliers.includes("EZON"), mustangSuppliers.join(","));

// Miata Streamline 2904C: Mazda Miata, core 2904C, Stayfast, $1,031.00, 5.5h.
const miata = ROWS.filter((r) =>
  r.make === "Mazda" && r.model === "Miata" && r.coreNumber === "2904C");
console.log("Miata 2904C rows:", miata.length);
miata.forEach((r) => console.log("  ", r.supplier, r.sku, "core", r.coreNumber,
  "material", JSON.stringify(r.material), "priceCents", r.priceMsrpCents,
  "labor", r.laborHours, "style", JSON.stringify(r.styleLabel)));
const sf = miata.find((r) => r.material && /stayfast/i.test(r.material));
check("Miata 2904C Stayfast row exists", !!sf, JSON.stringify(miata.map((r) => r.material)));
check("Miata 2904C Stayfast price == $1,031.00 (103100c)",
  !!sf && sf.priceMsrpCents === 103100, sf ? "got " + sf.priceMsrpCents : "no row");
check("Miata 2904C Stayfast labor == 5.5h",
  !!sf && sf.laborHours === 5.5, sf ? "got " + sf.laborHours : "no row");

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
