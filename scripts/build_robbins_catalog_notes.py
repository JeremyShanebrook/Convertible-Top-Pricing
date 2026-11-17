import json, re, collections

SRC = "/home/hatch/workspace/projects/convertible-top-app/data/_raw/robbins2026_book_entries.json"
OUT = "/home/hatch/workspace/ts-spaces/convertible-top-pricing-2/server/src/data/robbins_catalog.json"

def clean(s):
    return re.sub(r"\s+", " ", s or "").strip()

# ---- per-core notes from the book's own entry descriptions ----
entries = json.load(open(SRC))
core_notes = collections.defaultdict(list)
seen = collections.defaultdict(set)
for e in entries:
    desc = clean(e.get("description"))
    core = (e.get("part_no") or "").strip()
    if not core or len(desc) < 100:
        continue
    # skip pure cross-reference / price-table fragments
    if desc.lower().startswith("original topping"):
        pass  # original-topping lines are fitment info too; keep
    key = desc[:120]
    if key in seen[core]:
        continue
    seen[core].add(key)
    if len(core_notes[core]) >= 3:
        continue
    yrs = ""
    if e.get("year_start"):
        yrs = f"{e['year_start']}" + (f"\u2013{e['year_end']}" if e.get("year_end") and e["year_end"] != e["year_start"] else "")
    core_notes[core].append({
        "years": yrs,
        "page": e.get("page"),
        "text": desc[:800],
    })

general = {
    "source": "Robbins 2026 Price List (REV071626) \u2014 suggested retail prices effective March 1, 2026. Full book: https://robbinsautotop.com/media/robbinscatalog/2026/index.html",
    "importantInformation": [
        "Prices are in US Dollars and all transactions are payable in US Currency.",
        "Prices apply to products made in the listed materials and colors only. Robbins develops patterns to work with the original and/or most common toppings for each model. We cannot guarantee proper fit and performance of products ordered in materials which are not listed.",
        "Standard colors are subject to change based on availability.",
        "Non standard products will be Special Order/Non-Returnable, and cannot be canceled once production has started. Call Customer service for pricing on Special Order items.",
        "For Right Hand Drive Tonneau covers add an \u201cX\u201d to the core part # (1900HX).",
        "Labor Hours are approximate based on the time a skilled installer should take to install the item. Time to adjust, alter or repair the vehicle frame is not included.",
        "Special options such as non-original Hand Rolled Bindings; Brass Zippers; Charcoal Tint plastic windows and alternative materials are available. Please contact Robbins Customer Service for pricing.",
        "Supply chain disruption: To ensure our ability to continue supplying the best products and services when faced with supply chain constraints, we reserve the right to utilize alternative materials and production methodologies. We are committed to continue providing our customers industry leading products and warranties.",
        "NOTICE: As the premier global manufacturer of convertible tops, we have learned invaluable lessons during the COVID era. We have come to understand the critical necessity of having more than one source for raw materials, as we have encountered recurring supply chain disruptions. As a result, we have dedicated ourselves to developing additional materials that meet or exceed industry standards, as evidenced by rigorous laboratory testing. Our confidence in these new materials is so unwavering that we are proud to offer a 5-year material failure warranty. In the unlikely event that the material fails, we will replace the top.",
        "NEW for 2026: TopDown Auto introduces the New Sun-Fast\u00ae range of cloth toppings materials and will soon offer new vinyl toppings. Note that all HAARTZ 100% Cotton backed vinyl materials are superseded with 100% polyester \u201cForte\u201d backed vinyl material, except those with tan or gray backing, which will continue to be Cotton or Polyester/Cotton blend, respectively.",
        "For materials not listed, call Robbins Customer Service for availability and price.",
    ],
    "definitions": [
        "HRS \u2014 Approximate installation time (Hours).",
        "B/H \u2014 Required rear Bow Height for installation.",
        "Combo \u2014 Includes both the Front Top and Rear Window sections.",
        "N/A \u2014 Not Available. TBA \u2014 Pricing to be announced when product is released.",
        "For warranty, visit: www.robbinsautotop.com",
        "Technical support is provided for Authorized Distributors and Professional Trim Shops only. DIY (do it yourself) installation is not recommended.",
    ],
    "windowSystems": "Robbins\u2019 PermaLok Window Bonding System, established in 2011, is a specialized window bond engineered to meet rigorous factory-level standards, providing a fail-safe window integration. The Infinity Window System (introduced 2017) achieves the sleek, flush-to-fabric exterior seen on modern OEM tops, with continuous refinement to address early challenges and enhance bond integrity \u2014 a factory-style finish with optimized performance. (Robbins 2026 Price List, p. 84.)",
    "trimShopChecklist": [
        "Operation of the top frame: does the top raise and lower correctly, without irregular motion? Any wear spots or visible problems with the old top, window assembly or frame?",
        "Wear marks or holes: any wear marks, holes, or other visible problems with the existing top or frame?",
        "Power top frame wiring: check condition of convertible mechanism wiring. Be careful not to damage wiring when replacing the top. Report any existing damage to the customer.",
        "Cables: do side or rear cables need to be replaced?",
        "Bow height: is the bow height set correctly?",
        "Latches: do the top latches operate correctly?",
        "Door glass: are the door and quarter glass window alignments correct? Check that the old top does not hit door glass when doors are opened.",
        "Water leaks: check for water leaks, clogged drains, and water test before removing the old top.",
        "Weather strips: are these worn or damaged and need replacing? Most convertible top weather seals perform optimally for approximately three years.",
        "Top frame straps and pads: check for wear, sagging, etc. Always replace stay-pads or straps to avoid cuts and/or holes wearing or pinching through convertible top fabric. Many convertible models have well documented issues that result from aging or worn stay-pads or straps.",
        "If the power top frame uses a hydraulic system: check for leaks in cylinders, reservoir, hoses and fittings; check fluid levels; check that the motor runs and sounds and smells normal (no burning odor).",
        "Walk around the car with the owner and document any scratches, dings, dents, etc. Note these on a diagram or separate sheet for the customer to initial.",
        "Look at paint and molding in the area you will be working and check for rust or other damage.",
        "Protect yourself: explain to the convertible owner that \u201chidden\u201d damage may exist which cannot be seen until the top and/or window assembly has been removed \u2014 e.g. damaged or deteriorated tack strips, rusted, broken or bent top frame components.",
    ],
    "typicalDiagrams": [
        {"figure": "Figure A \u2014 Top Frame", "text": "Second Bow, Third Bow, Rear Bow, Tack Rail, Diagonal or Vertical Top Frame Member, Horizontal Side Member, Front Side Member, Header Bow."},
        {"figure": "Figure B \u2014 Typical American Car Top, Outside View", "text": "Deck, Quarter, Welt, Tip, Wire-On, Valance, Belt Moulding."},
        {"figure": "Figure C \u2014 Typical Rear Curtain Assembly", "text": "Shows partial Top Pads, Quarter Pads, and Tack Rail: Top Pads, Glass or Plastic window, Bottom Color Trim, Quarter Pads, White Trace Lines or Guide Marks."},
        {"figure": "Figure D \u2014 Typical American Car Top, Showing Installation", "text": "Deck Seam (Quarters), Staples (shown diagonally), White Trace Lines."},
        {"figure": "Figure E \u2014 Top, Inside View", "text": "Horizontal Front Quarter Flap, Side Tension Cable Sleeve, Reinforcement (typical around edges of top), Vertical Quarter Flap, Rear Retainer Sleeve or Retainer Flap, Listing (Rear Bow), Listing (Third Bow), Listing (Second Bow)."},
        {"figure": "Figure F \u2014 Typical Import Car Top with Frame", "text": "Mounted Door Glass Weather seals, Top Stitching, Deck Seam (Quarters), Deck Seam (Back Window Section)."},
        {"figure": "Figure G \u2014 Typical Import Car Top, with Flaps, Rainguard, and Skirt (British Style)", "text": "Skirt, Rear Quarter Window, Door Glass Flap, Center Window, Back Window Section, Deck, Quarter, Rainguard, Header Bow Pocket."},
    ],
}

# ---- curated vehicle-level notes / disclaimers (verbatim from the book) ----
# Match rules use canonical make/model as the app computes them, plus core numbers.
VN = [
 {"title": "Bentley Continental \u2014 repair kit notice & disclaimer (Robbins 2026, p. 6)",
  "cores": ["2452C", "2452CRK", "2452"], "makes": ["Bentley"], "modelIncludes": ["Continental"], "yearStart": None, "yearEnd": None,
  "text": "IMPORTANT NOTICE: Replacement top 2452C is designed only for vehicles already equipped with OEM Repair Kit #3W7898014BRK2452. Before purchasing a new top, verify that the repair kit was pre-installed on the frame. If the repair kit is not present, use convertible top #2452CRK which includes the Repair Kit. DISCLAIMER: Robbins is not responsible for damage caused by the vehicle\u2019s original mechanism design. Please note that damage has been reported even on vehicles where the repair kit is present."},
 {"title": "Camaro / Firebird 1994\u20132002 \u2014 disclaimer (Robbins 2026, pp. 19 & 64)",
  "cores": ["7210C", "7210"], "makes": ["Chevrolet", "Pontiac"], "modelIncludes": ["Camaro", "Firebird"], "yearStart": 1994, "yearEnd": 2002,
  "text": "DISCLAIMER: A.S.C. and General Motors have modified the 1994-2002 Camaro Top and Glass Window to eliminate damage to tops and broken glass windows caused by problems in the top frame design. Robbins cannot be held responsible for cuts, holes, broken glass, etc., caused by the manufacturer\u2019s design of the top or top frame."},
 {"title": "Camaro 2011\u20132015 \u2014 disclaimer (Robbins 2026, p. 20)",
  "cores": ["7220C", "7220"], "makes": ["Chevrolet"], "modelIncludes": ["Camaro"], "yearStart": 2011, "yearEnd": 2015,
  "text": "DISCLAIMER: GM has made several running corrections to 2011-2015 Camaro Tops in an effort to eliminate inherent problems with the original design. Service Bulletins have been issued to address problems with fit, operation, water leaks, and other issues. Robbins cannot be held responsible for problems caused by the original manufacturer\u2019s design of the top or top frame."},
 {"title": "Mercedes SL (R129) \u2014 no warranty against plastic-window creasing/cracking (Robbins 2026, p. 46)",
  "cores": ["2042R", "3152R", "2042"], "makes": ["Mercedes-Benz", "Mercedes"], "modelIncludes": ["SL", "300SL", "500SL", "600SL"], "yearStart": 1990, "yearEnd": 2002,
  "text": "NO WARRANTY AGAINST: Creasing or cracking of plastic windows in 2042R Tops or 3152R Rear Window Assemblies. Service Bulletins 77/26A and 77/39 have been issued by Mercedes Benz describing abrasion, pinching, cuts, holes, tearing and other damage to the topping and seams in the front top section and rear window assembly; as well as fraying, creasing and breaking of plastic windows caused by the top frame and body components. Robbins cannot be held responsible for damage to our products caused by problems described above."},
 {"title": "Mitsubishi Eclipse \u2014 frame caution & service bulletins (Robbins 2026, p. 49)",
  "cores": ["2475C", "2476C", "2477C"], "makes": ["Mitsubishi"], "modelIncludes": ["Eclipse"], "yearStart": 1996, "yearEnd": 2009,
  "text": "CAUTION: 1996-99 Eclipse frame components can bend, which may cause abrasion damage, cuts and holes. Mitsubishi has issued Instruction Sheet 8715 that describes the left and right frame links (MR328561 and MR328562) and elastic straps (MR311161) that should be replaced to prevent the top frame damaging the top. Subsequent Technical Service Bulletins have been issued related to this and other issues: (TSB-99-42A-001, TSB-99-42A-002, TSB-99-42A-007, TSB-99-42A-0019). Robbins is not responsible for any damage that may result from flawed OEM design."},
 {"title": "Nissan 350Z \u2014 TSB notice (Robbins 2026, p. 55)",
  "cores": ["2150", "2150C"], "makes": ["Nissan"], "modelIncludes": ["350Z"], "yearStart": 2003, "yearEnd": 2009,
  "text": "350Z NOTICE: Nissan has issued multiple TSB\u2019s (Technical Service Bulletins) to address known issues with 350Z convertible tops. Robbins is not responsible for problems resulting from vehicle design flaws. TSB numbers include NTB03-104A, NTB03-122, NTB03-121, NTB03-120, NTB08-100. (TSB #NTB08-100 regarding \u201cTop does not fully open\u201d calls for replacing elastic bow straps. In our experience this has not fixed the problem. We have observed this problem most frequently in 2004 models, for which we have developed \u2018secondary elastic straps\u2019 to prevent. In most cases these help, but may not prevent the problem in all cases.)"},
 {"title": "Nissan 370Z \u2014 bungee kit requirement & TSB notice (Robbins 2026, p. 55)",
  "cores": ["2151C", "2151CK", "2151"], "makes": ["Nissan"], "modelIncludes": ["370Z"], "yearStart": 2010, "yearEnd": 2020,
  "text": "NOTICE: Must install Bungee 5th Bow Repair Kit (not included) to avoid hard tonneau cover hitting soft top at 5th bow and causing damage. 370Z NOTICE: Nissan has issued TSB #NTB19-061 to address known issues with 370Z convertible tops rubbing on storage lid when opening and causing cut/holes in the top. Nissan recommends installing the 5th Bow Bungee Kit to address these problems. There have been reports of vehicles exhibiting cuts/holes as described above even after installation of the 5th Bow Bungee Kit. Robbins is not responsible for problems that are inherent to the vehicle\u2019s OEM design."},
 {"title": "Mazda Miata \u2014 heated-glass connector notice (Robbins 2026, p. 43)",
  "cores": [], "makes": ["Mazda"], "modelIncludes": ["Miata", "MX-5"], "yearStart": 1992, "yearEnd": 1997,
  "text": "NOTICE: For 1992\u201397 MX-5 Miata models not equipped with a heated-glass hardtop, a Mazda OEM 3-wire connector (Part #N007-67-060A) is required to use our heated glass tops. This connector is available through Mazda dealers in the U.S. for approximately $200. *Note: 1991 and earlier models are not factory-wired for a rear defogger."},
 {"title": "Porsche 911 Targa \u2014 pattern note (Robbins 2026, p. 67)",
  "cores": ["2008", "2008R"], "makes": ["Porsche"], "modelIncludes": ["911", "Targa"], "yearStart": 1967, "yearEnd": 1994,
  "text": "NOTE: Due to running changes made by Porsche, our Targa pattern is approximate and may require additional fitting time."},
 {"title": "Triumph \u2014 commission numbers & bow-straps notice (Robbins 2026, p. 75)",
  "cores": [], "makes": ["Triumph"], "modelIncludes": [], "yearStart": None, "yearEnd": None,
  "text": "NOTICE: Model year alone is not sufficient to determine the correct product for some applications. Use Commission Numbers to help you select the correct product per application. Commission number plate is located on the right side of the vehicle\u2019s bulkhead. (Details on many cars have been changed by car owners over time. We are not responsible for product incompatibility resulting from this). Most Triumph tops require replacement bow-straps and/or Velcro as part of the installation. These items are not included with our tops, nor are they reflected in our approximated installation hours."},
 {"title": "Jaguar XJS Hess & Eisenhardt \u2014 refurbished glass window terms (Robbins 2026, p. 40)",
  "cores": ["HD219", "2419"], "makes": ["Jaguar"], "modelIncludes": ["XJS"], "yearStart": 1988, "yearEnd": 1988,
  "text": "Refurbished Glass Rear Window for 2419 Top (HD219): Customer Must Supply Original Glass to be installed in new window curtain. No warranty. We cannot accept responsibility for damage of any kind, including while in our possession. Must obtain reference number from Robbins before sending original glass. Does not fit Baur conversion."},
 {"title": "Audi A4 / S4 Cabriolet \u2014 abrasion caution (Robbins 2026, p. 3)",
  "cores": ["3201C", "3201"], "makes": ["Audi"], "modelIncludes": ["A4", "S4"], "yearStart": 2003, "yearEnd": 2009,
  "text": "CAUTION: The design of the Audi A4 top and frame assembly may cause abrasion damage to the topping over time; that in extreme cases could result in cuts or holes in tops. Robbins cannot be held responsible for any damage to our products caused by the problems described above."},
 {"title": "Audi TT 2000\u201306 \u2014 rain rail notice (Robbins 2026, p. 3)",
  "cores": ["3220C", "3220"], "makes": ["Audi"], "modelIncludes": ["TT"], "yearStart": 2000, "yearEnd": 2006,
  "text": "NOTICE: 2000-06 Audi TT factory original Rain Rail bond dries and becomes brittle over time, which eventually leads to failure. Rain rail bond failure will result in severe damage to the vehicle\u2019s electrical system upon water penetration. Although rain rail removal is not a required step when replacing the convertible top, it is recommended that it be removed and securely reattached to the interior body at this time, to help the car owner avoid costly electrical system repairs."},
 {"title": "BMW Z3 \u2014 cable length caution & abrasion notice (Robbins 2026, p. 9)",
  "cores": ["2750C", "2750"], "makes": ["BMW"], "modelIncludes": ["Z3"], "yearStart": 1996, "yearEnd": 2002,
  "text": "CAUTION: Regarding Z3 Cables: We have found that BMW\u2019s documented change period (12/1996) from SHORT cables to LONG cables is not absolute. Therefore, before removing the old top from the car, it is necessary to verify that the side tension cables match the OAL length (Overall Length) listed in the Robbins product description. Note: The BMW dealer\u2019s Serial Number based product selection Does Not ensure correct cable identification. NOTICE: Regarding Z3 Tops: Severe abrasion of topping, which may lead to cuts and holes developing in tops, and severe creasing of plastic windows can occur due to the design of the top frame assembly, body components and top. Robbins cannot be held responsible for any damage to our products caused by problems described above."},
 {"title": "Chevy Cavalier 1995-on \u2014 GM bulletin caution (Robbins 2026, p. 21)",
  "cores": [], "makes": ["Chevrolet", "Pontiac"], "modelIncludes": ["Cavalier", "Sunfire"], "yearStart": 1995, "yearEnd": 2005,
  "text": "CAUTION: Technical Bulletins 63-10-49 and 63-15-15 have been issued by GM describing problems with Top frames in 1995-On Cavalier models. There have also been reports of rear seat backrest being bent out of shape which can cause the Headliner and Top to snag when the Top and Glass Window are lowered, causing listings to fail and cuts and holes to develop in the Top. Robbins cannot be held responsible for damage to our products by the causes described above."},
 {"title": "Chrysler LeBaron 1987\u201395 \u2014 service bulletin notice (Robbins 2026, p. 25)",
  "cores": [], "makes": ["Chrysler"], "modelIncludes": ["LeBaron"], "yearStart": 1987, "yearEnd": 1995,
  "text": "NOTICE: Chrysler issued Service Bulletin 23-23-89/P-3754 (and others) describing cuts and holes in top caused by abrasion or pinching of top by 1987-95 LeBaron top frames, and the repair procedures which dealers need to perform. Robbins cannot be held responsible for damage caused to our products by top frames, body components or the design of the convertible top."},
 {"title": "Ford Mustang 1989 \u2014 service bulletin notice (Robbins 2026, p. 35)",
  "cores": [], "makes": ["Ford"], "modelIncludes": ["Mustang"], "yearStart": 1989, "yearEnd": 1989,
  "text": "NOTICE: Service Bulletin 90-6-2 has been issued by the manufacturer advising of problems in 1989 Mustang top frames which can cut or tear convertible tops; and the repair procedures which are required. Robbins cannot be held responsible for damage which may occur as a result of the manufacturer\u2019s design of tops and top frames."},
 {"title": "Porsche Boxster \u2014 cable & drive notices (Robbins 2026, p. 70)",
  "cores": ["3161", "3162", "3163", "3164", "3165"], "makes": ["Porsche"], "modelIncludes": ["Boxster"], "yearStart": 1997, "yearEnd": 2012,
  "text": "CAUTION: Porsche has issued Service Bulletin Group 6-61 28 55, describing problems with the cable sleeve channel hanging up when the top is raised or lowered, that can cause side cables to tear away from the top. The bulletin further describes new parts that need to be installed and repairs that need to be made to the frame to correct this problem. Robbins cannot be held responsible for side cables tearing out of our 3161 and 3162 tops as a result of this frame problem. NOTICE: There are known issues with Porsche Boxster convertible top motor gears wearing, convertible transmission arms bending, and convertible transmission cables repeatedly popping off of arms. Occurrences have been reported in vehicles with OEM and other convertible top makes. Robbins cannot be held responsible for these known issues."},
 {"title": "Saab \u2014 frame pinching caution & glass clip warning (Robbins 2026, p. 71)",
  "cores": ["2725", "2725C", "2728R", "2732C", "2735C"], "makes": ["Saab"], "modelIncludes": ["900", "9-3"], "yearStart": 1987, "yearEnd": 2009,
  "text": "CAUTION Regarding 2725: Saab has issued Service Bulletin 03/93-0316 for 1987-93 Saab convertibles advising that top frame components can cause pinching of the top, and that abrasion damage, cuts, and holes can occur. Robbins cannot be held responsible for any damage to our products caused by the problems described above. WARNING Regarding 2728R, 2732C, 2735C Tops: Be extremely careful removing clips that attach glass, rubber weather seal and metal retainers to old top. Do not lose any clips and be careful not to scratch or chip the glass. Place shop blanket on bench to protect glass, and be extremely careful when installing glass, rubber weather seal and retainers in top with clips."},
 {"title": "Volkswagen Thing \u2014 top frame notice (Robbins 2026, p. 78)",
  "cores": ["2065"], "makes": ["Volkswagen", "VW"], "modelIncludes": ["Thing"], "yearStart": None, "yearEnd": None,
  "text": "NOTICE: Volkswagen Thing top frames have several problems resulting from their fragile construction. Top frames sag and bend as a result of weak hinge points and side rails made of thin gauge steel, and rivet holes elongate causing frames to shift. These problems often cause tops to fit poorly if not corrected by a VW Thing specialist."},
]

# ---- reference diagrams (Robbins 2026, pp. 80-81) with match rules ----
RD = [
 {"title": "Reference diagram \u2014 Fiat 124 CS1 / CS2 deck-seam measurement (Robbins 2026, p. 80)",
  "cores": ["2032", "2032A", "3002", "3002A"], "makes": ["Fiat", "Toyota"], "modelIncludes": ["124", "Celica", "Spider"], "yearStart": None, "yearEnd": None,
  "text": "Measurement between Deck Seams, across rear bow: 36 \u00bc Inches = Part No. 3002; 36 \u00be Inches = Part No. 3002A. Use this measurement to identify the correct top for Fiat 124-CS1 and 124-CS2 and Toyota Celica Wide Deck and Narrow Deck applications. Part # 2032: 1969-85 Fiat CS1-124 1400, 1600, 1800, Spider. Part # 2032A: 1979-85 Fiat CS2-124 2000 Spider."},
 {"title": "Reference diagram \u2014 Mercedes R129 rear-bow flaps (Robbins 2026, p. 80)",
  "cores": ["2039R", "2037R", "2039", "2037"], "makes": ["Mercedes-Benz", "Mercedes"], "modelIncludes": ["SL", "300SL", "500SL", "600SL"], "yearStart": 1990, "yearEnd": 2002,
  "text": "Flaps for Early Models: 2039R top \u2014 Listing glues to Metal Rear Bow (no exterior feature strip), 50 Gauge Plastic Windows. 2037R top \u2014 Listing uses an exterior feature strip and staples to Wooden Rear Bow. Compare your car\u2019s rear bow before ordering."},
 {"title": "Reference diagram \u2014 Dimension \u201cA\u201d for part numbers 6215 / 6216 (Robbins 2026, p. 80)",
  "cores": ["6215", "6216"], "makes": [], "modelIncludes": [], "yearStart": None, "yearEnd": None,
  "text": "Dimension A (see the book\u2019s reference diagram): Part No. 6215 \u2014 23 5/8 inches. Part No. 6216 \u2014 25 inches. Measure dimension A on the existing top to select the correct part."},
 {"title": "Reference diagram \u2014 1968-72 GM Mid-size: 7304 vs 7304A (Robbins 2026, p. 81)",
  "cores": ["7304", "7304A"], "makes": ["Buick", "Chevrolet", "Oldsmobile", "Pontiac"], "modelIncludes": [], "yearStart": 1968, "yearEnd": 1972,
  "text": "1968-72 GM Mid-size Convertibles: 7304 convertible top is notched at the bottom of the B-Pillars, and 7304A top is straight. Before placing your order, compare the existing top to the diagram and order the top that matches closest. Note that Robbins is not responsible for incorrect products being ordered."},
 {"title": "Reference diagram \u2014 1987-93 Camaro & Firebird measurement table (Robbins 2026, p. 81)",
  "cores": ["7203", "7204", "7205", "7206"], "makes": [], "modelIncludes": [], "yearStart": 1987, "yearEnd": 1993,
  "text": "Due to undocumented production changes by A.S.C. and GM, selecting a replacement top requires measuring your current, properly fitted top. All measurements are in inches. A: 7203 \u2014 42\u00bd, 7204 \u2014 42\u00bd, 7205 \u2014 42\u00bd, 7206 \u2014 45\u00bd. B: 7203 \u2014 41, 7204 \u2014 41, 7205 \u2014 41\u215e, 7206 \u2014 44. C: 7203 \u2014 50, 7204 \u2014 52\u00bc, 7205 \u2014 50\u00be, 7206 \u2014 50\u00bd\u201351. Note: Measurements are based on original equipment (OEM) dimensions. If your current top is not an OEM or Robbins brand (the only known OEM-spec product produced today) we cannot guarantee precise identification. Special Order Notice: 7203, 7204, 7205, 7206 are non-returnable (Exception: 7206 in Black Stayfast)."},
 {"title": "Reference diagram \u2014 GL401/402 Non-Original GM Glass (Robbins 2026, p. 81)",
  "cores": ["GL401", "GL402"], "makes": ["Buick", "Cadillac", "Chevrolet", "Oldsmobile", "Pontiac"], "modelIncludes": [], "yearStart": 1961, "yearEnd": 1967,
  "text": "1961-64 GM Full-size & 1962-67 GM Mid-size Convertibles: Glass is smaller than original plastic window and has exposed color trim on all sides, as shown in the diagram. Top does not cover edges of glass; curtain and edges of glass are exposed (reverse fold, heat-sealed and top stitched edge). Note that GL401 must be unzipped before lowering top. Trimmer may have to make a deeper well liner to fit glass."},
 {"title": "Reference diagram \u2014 Aston Martin DB9 Volante rear-window position (Robbins 2026, p. 81)",
  "cores": ["2560AC", "2560BC", "2560A", "2560B"], "makes": ["Aston Martin"], "modelIncludes": ["DB9"], "yearStart": 2014, "yearEnd": 2016,
  "text": "2014-16 Aston Martin DB9 Volante: Two convertible top variations have been identified, believed to be due to a running change by the OEM. The two tops are distinguishable by the rear window position. Measure from the bottom edge of the glass (not the DLO) to bottom edge of binding at center. If measurement is 3\u2033 order part #2560AC. If measurement is 6\u2033 order part #2560BC."},
 {"title": "Reference diagrams \u2014 Mercedes W113 & Mercury Capri (Robbins 2026, p. 80)",
  "cores": [], "makes": ["Mercedes-Benz", "Mercedes", "Mercury"], "modelIncludes": ["230SL", "250SL", "280SL", "Capri"], "yearStart": 1963, "yearEnd": 1994,
  "text": "The book\u2019s Reference Diagrams page (p. 80) carries model-specific diagrams for the Mercedes W113 (230SL/250SL/280SL) and the Mercury Capri \u2014 consult the diagram for your model in the Robbins 2026 Price List before ordering, and compare the existing top\u2019s rear-bow and listing arrangement to the diagram."},
]

out = {"general": general, "coreNotes": dict(core_notes), "vehicleNotes": VN, "referenceDiagrams": RD}
json.dump(out, open(OUT, "w"), indent=1, ensure_ascii=False)
import os
print("cores with notes:", len(core_notes), "total notes:", sum(len(v) for v in core_notes.values()))
print("file size KB:", os.path.getsize(OUT)//1024)
