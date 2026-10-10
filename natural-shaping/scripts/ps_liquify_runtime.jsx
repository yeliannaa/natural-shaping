/* Photoshop 2020 / ExtendScript ES3. Load before ps_retouch_runtime.jsx.
   Only the measured LqFy faceMesh and LqMe v4 routes are available.
   Executing a command is not pixel or aesthetic acceptance. */
var NativeLiquify = (function () {
    var VERSION = "1.0.7", MAX_MESH_BYTES = 134217728;
    var FACE_KEYS = ["leftEyeSize", "rightEyeSize", "leftEyeHeight", "rightEyeHeight",
        "leftEyeWidth", "rightEyeWidth", "leftEyeTilt", "rightEyeTilt", "eyeDistance",
        "smile", "upperLip", "lowerLip", "mouthWidth", "noseWidth", "faceWidth",
        "chinHeight", "jawShape", "mouthHeight", "noseHeight", "foreheadHeight"];
    function c(v) { return charIDToTypeID(v); }
    function s(v) { return stringIDToTypeID(v); }
    function fail(v) { throw new Error("NativeLiquify: " + v); }
    function num(v, lo, hi, label) { if (typeof v !== "number" || !isFinite(v) || v < lo || v > hi) fail("Invalid " + label); return v; }
    function info(d) { return { name: d.name, width: d.width.as("px"), height: d.height.as("px"), bits: String(d.bitsPerChannel), mode: String(d.mode), profile: d.colorProfileName }; }
    function invariant(d, before) { var now = info(d); if (now.width !== before.width || now.height !== before.height || now.bits !== before.bits || now.mode !== before.mode || now.profile !== before.profile) fail("Dimensions, depth, mode or profile changed"); }
    function probe(d) { return { loaded: true, version: VERSION, photoshopVersion: app.version, document: d ? info(d) : null, commandExecuted: false, pixelEffectUnverified: true, faceControls: ["faceWidth"], meshVersion: 4, meshGridPixels: 4 }; }
    function rgb(d) { d.activeChannels = [d.channels[0], d.channels[1], d.channels[2]]; }
    function layerHits(d, selector) {
        var hits = [];
        function walk(container) { var i, l; for (i = 0; i < container.layers.length; i++) { l = container.layers[i]; if ((selector.id !== undefined && l.id === selector.id) || (selector.id === undefined && l.name === selector.name)) hits.push(l); if (l.typename === "LayerSet") walk(l); } }
        walk(d); return hits;
    }
    function selector(v, label) {
        if (!v || typeof v !== "object" || v instanceof Array) fail(label + " needs id or unique name");
        var k; for (k in v) if (v.hasOwnProperty(k) && k !== "id" && k !== "name") fail("Unsupported " + label + " field: " + k);
        if (v.id !== undefined) { num(v.id, 1, 2147483647, label + " id"); if (v.id !== Math.floor(v.id)) fail(label + " id must be integer"); }
        else if (typeof v.name !== "string" || !v.name) fail(label + " needs id or unique name");
    }
    function target(d, ref) { var hits = layerHits(d, ref); if (hits.length !== 1) fail("Layer selector must match exactly once"); return hits[0]; }
    function layerDescriptor(d, l) { var ref = new ActionReference(); ref.putIdentifier(c("Lyr "), l.id); ref.putIdentifier(c("Dcmn"), d.id); return executeActionGet(ref); }
    function flag(desc, key) { return desc.hasKey(s(key)) && desc.getBoolean(s(key)); }
    function opaqueBackground(d) {
        // Bounds cannot prove opacity. A genuine Photoshop Background cannot
        // contain transparent pixels; the following restrictions preserve that
        // guarantee when it is included in the visible composite.
        var i, l, desc;
        for (i = 0; i < d.layers.length; i++) {
            l = d.layers[i];
            if (l.typename === "ArtLayer" && l.isBackgroundLayer === true && l.visible && l.opacity === 100 && l.fillOpacity === 100 && l.blendMode === BlendMode.NORMAL) {
                desc = layerDescriptor(d, l);
                if (!flag(desc, "hasUserMask") && !flag(desc, "hasVectorMask") && !desc.hasKey(s("layerEffects"))) return { id: l.id, name: l.name };
            }
        }
        fail("mergedVisible requires a visible root-level Photoshop Background at normal 100 percent without masks or effects; canvas bounds do not prove alpha opacity");
    }
    function visibleDependencies(d) {
        var out = [];
        function walk(container, groupPath) {
            var i, l, desc, entry, childPath;
            for (i = 0; i < container.layers.length; i++) {
                l = container.layers[i]; if (!l.visible) continue; desc = layerDescriptor(d, l);
                entry = { id: l.id, name: l.name, typename: l.typename, groupPath: groupPath.slice(0), opacity: l.opacity, fillOpacity: l.typename === "ArtLayer" ? l.fillOpacity : null, blendMode: String(l.blendMode), hasUserMask: flag(desc, "hasUserMask"), hasVectorMask: flag(desc, "hasVectorMask"), hasLayerEffects: desc.hasKey(s("layerEffects")) }; out.push(entry);
                if (l.typename === "LayerSet") { childPath = groupPath.slice(0); childPath.push(l.id); walk(l, childPath); }
            }
        }
        walk(d, []); return out;
    }
    function bounds(l) { var b = l.bounds, out = [], i; for (i = 0; i < 4; i++) out.push(b[i].as("px")); return out; }
    function fullCanvas(l, d) { var b = bounds(l); if (b[0] !== 0 || b[1] !== 0 || b[2] !== d.width.as("px") || b[3] !== d.height.as("px")) fail("Source and result pixel bounds must match the full canvas exactly"); return b; }
    function roi(d, r) {
        if (!(r instanceof Array) || r.length !== 4) fail("ROI needs [left,top,right,bottom]");
        var w = d.width.as("px"), h = d.height.as("px"); num(r[0], 0, w, "ROI left"); num(r[1], 0, h, "ROI top"); num(r[2], 0, w, "ROI right"); num(r[3], 0, h, "ROI bottom"); if (r[0] >= r[2] || r[1] >= r[3]) fail("Empty ROI");
    }
    function operation(d, op) {
        if (!op || (op.type !== "liquifyFace" && op.type !== "liquifyMesh")) fail("Only liquifyFace and liquifyMesh are supported");
        var allowed = { type: 1, name: 1, source: 1, target: 1, parent: 1, opacity: 1, visible: 1, mask: 1, roi: 1, feather: 1 }, k;
        allowed[op.type === "liquifyFace" ? "faceWidth" : "meshPath"] = 1;
        for (k in op) if (op.hasOwnProperty(k) && !allowed[k]) fail("Unsupported " + op.type + " field: " + k);
        if (typeof op.name !== "string" || !op.name || op.name === "__RET_RUNTIME_WORK__" || /[\x00-\x1f]/.test(op.name)) fail("A safe new layer name is required");
        if (d.mode !== DocumentMode.RGB || (d.bitsPerChannel !== BitsPerChannelType.EIGHT && d.bitsPerChannel !== BitsPerChannelType.SIXTEEN)) fail("RGB8 or RGB16 document required");
        var source = op.source === undefined ? "mergedVisible" : op.source;
        if (source !== "mergedVisible" && source !== "target") fail("source must be mergedVisible or target");
        if (source === "mergedVisible" && op.parent !== undefined) fail("mergedVisible does not allow parent: its snapshot must remain at the document root above all visible content");
        if (source === "target") {
            selector(op.target, "target");
            if (op.mask !== undefined && op.mask !== "white") fail("target replacement supports no mask or white only; a local mask could discard donor content");
            if (op.opacity !== undefined && op.opacity !== 100) fail("target replacement opacity must be 100 to preserve donor alpha");
            if (op.visible !== undefined && op.visible !== true) fail("target replacement must be visible; comparison requires hiding the new layer and restoring donor visibility explicitly");
        } else if (op.target !== undefined) fail("target requires source: target");
        if (op.parent !== undefined) selector(op.parent, "parent");
        num(op.opacity === undefined ? 100 : op.opacity, 0, 100, "opacity");
        if (op.visible !== undefined && typeof op.visible !== "boolean") fail("visible must be boolean");
        if (op.mask !== undefined && op.mask !== "roi" && op.mask !== "white" && op.mask !== "black") fail("mask must be roi, white or black");
        if (op.mask === "roi") { roi(d, op.roi); num(op.feather === undefined ? 0 : op.feather, 0, Math.min(op.roi[2] - op.roi[0], op.roi[3] - op.roi[1]) / 2, "mask feather"); }
        else if (op.roi !== undefined || op.feather !== undefined) fail("roi and feather require mask: roi; the filter always uses the full canvas");
        if (op.type === "liquifyFace") num(op.faceWidth, -1, 1, "faceWidth (the only measured face control)");
        return source;
    }
    function safePath(p, isFile) {
        if (typeof p !== "string" || !p || /[\x00-\x1f%]/.test(p)) fail("Input must use a literal absolute path");
        var v = p.split("\\").join("/"), parts = v.split("/"), i;
        if (!/^[A-Za-z]:\//.test(v) && (v.charAt(0) !== "/" || v.charAt(1) === "/")) fail("Input must use an absolute local path");
        if (v.indexOf("//") >= 0) fail("UNC, URI and repeated path separators are not supported");
        for (i = 0; i < parts.length; i++) { if (parts[i] === "." || parts[i] === "..") fail("Input path traversal is forbidden"); if (i > 0 && parts[i].indexOf(":") >= 0) fail("Input path stream or URI is forbidden"); }
        var f = isFile ? new File(p) : new Folder(p), parent = isFile ? f.parent : f, n = 0, prior = "";
        if (f.alias) fail("Input aliases are forbidden");
        while (parent && parent.fsName !== prior) { if (parent.alias) fail("Input directory aliases are forbidden"); prior = parent.fsName; parent = parent.parent; if (++n > 512) fail("Input parent chain is invalid"); }
        var canonical = f.fsName.split("\\").join("/").toLowerCase(); while (canonical.length > 1 && canonical.charAt(canonical.length - 1) === "/") canonical = canonical.substring(0, canonical.length - 1);
        return { file: f, canonical: canonical };
    }
    function meshFile(p, ctx) {
        var entry = safePath(p, true), file = entry.file, allowed = false, roots = [], i, root;
        if (!/\.msh$/i.test(p)) fail("meshPath must name a task .msh file");
        if (ctx && ctx.dir) roots.push(ctx.dir.fsName);
        if (ctx && ctx.allowlistedInputDirs !== undefined) {
            if (!(ctx.allowlistedInputDirs instanceof Array)) fail("allowlistedInputDirs must be an array");
            for (i = 0; i < ctx.allowlistedInputDirs.length; i++) roots.push(ctx.allowlistedInputDirs[i]);
        }
        for (i = 0; i < roots.length; i++) { root = safePath(roots[i], false); if (!root.file.exists) fail("Allowlisted input directory does not exist"); if (entry.canonical.indexOf(root.canonical + "/") === 0) allowed = true; }
        if (!allowed) fail("meshPath is outside the task directory and allowlistedInputDirs");
        if (!file.exists) fail("Mesh file not found");
        if (file.length < 64 || file.length > MAX_MESH_BYTES) fail("Mesh size is outside the supported range");
        return file;
    }
    function parseMesh(raw, d) {
        var at = 0, len = raw.length;
        function readByte(index) { return raw.charCodeAt(index) & 255; }
        function u32() { if (at + 4 > len) fail("Truncated mesh integer"); var v = readByte(at) + readByte(at + 1) * 256 + readByte(at + 2) * 65536 + readByte(at + 3) * 16777216; at += 4; return v; }
        function f32() {
            if (at + 4 > len) fail("Truncated mesh float");
            var b0 = readByte(at), b1 = readByte(at + 1), b2 = readByte(at + 2), b3 = readByte(at + 3), exponent = (b3 & 127) * 2 + (b2 >> 7), fraction = (b2 & 127) * 65536 + b1 * 256 + b0; at += 4;
            if (exponent === 255) fail("Mesh contains a non-finite displacement");
            return (b3 >= 128 ? -1 : 1) * (exponent === 0 ? fraction * Math.pow(2, -149) : (1 + fraction / 8388608) * Math.pow(2, exponent - 127));
        }
        if (len < 64 || readByte(0) !== 0 || readByte(1) !== 0 || readByte(2) !== 0 || readByte(3) !== 4 || raw.substring(4, 12) !== "yfqLhseM") fail("Only measured LqMe mesh v4 with yfqLhseM magic is supported");
        var w = d.width.as("px"), h = d.height.as("px");
        if (w !== Math.floor(w) || h !== Math.floor(h) || w < 4 || h < 4 || w % 4 || h % 4) fail("Measured v4 mesh requires canvas width and height divisible by four");
        var expected = [2, w / 4, h / 4, 0, 1, 0, 0, h, w, 0, 0, h, w], header = [], i;
        at = 12; for (i = 0; i < 13; i++) { header.push(u32()); if (header[i] !== expected[i]) fail("Mesh header, canvas dimensions or mesh dimensions do not match the measured v4 format"); }
        if (len > 64 + expected[2] * (expected[1] * 16 + 4)) fail("Mesh is larger than legal row RLE");
        var row, column, zeros, count, pair, dx, dy, nonzero = 0, runs = 0, max = 0;
        for (row = 0; row < expected[2]; row++) {
            column = 0;
            while (column < expected[1]) {
                zeros = u32(); if (zeros > expected[1] - column) fail("Mesh zero run exceeds row width"); column += zeros; runs++;
                if (column === expected[1]) break;
                count = u32(); if (!count || count > expected[1] - column) fail("Mesh nonzero run is empty or exceeds row width");
                if (at + count * 8 > len) fail("Truncated mesh displacement run");
                for (pair = 0; pair < count; pair++) { dx = f32(); dy = f32(); if (dx === 0 && dy === 0) fail("Zero displacement pair must use the zero run"); max = Math.max(max, Math.abs(dx), Math.abs(dy)); }
                column += count; nonzero += count;
            }
        }
        if (at !== len) fail("Unexpected mesh trailer; Face tails and other formats are unsupported");
        return { version: 4, magic: "yfqLhseM", headerBytes: 64, bytes: len, imageWidth: w, imageHeight: h, meshWidth: expected[1], meshHeight: expected[2], gridPixels: 4, nonzeroPairs: nonzero, zeroRuns: runs, maxAbsGridDisplacement: max, maxAbsSamplingPixels: max * 4, samplingDirection: "inverse", faceTrailer: false };
    }
    function validateInput(d, op, ctx) {
        var source = operation(d, op), out = { source: source };
        if (op.type === "liquifyFace") { var values = {}, j; for (j = 0; j < FACE_KEYS.length; j++) values[FACE_KEYS[j]] = FACE_KEYS[j] === "faceWidth" ? op.faceWidth : 0; out.parameters = { faceWidth: op.faceWidth, featureValues: values, faceDescriptorVersion: 2, faceMeshVersion: 2 }; }
        else {
            var file = meshFile(op.meshPath, ctx), raw;
            file.encoding = "BINARY"; if (!file.open("r")) fail("Cannot read mesh file");
            try { raw = file.read(); } finally { file.close(); }
            if (raw.length !== file.length) fail("Mesh file length changed while reading");
            out.mesh = parseMesh(raw, d); out.mesh.path = file.fsName; out.raw = raw;
        }
        if (source === "mergedVisible") out.opaqueBackground = opaqueBackground(d);
        return out;
    }
    function faceDescriptor(amount) {
        var values = new ActionDescriptor(), featureInfo = new ActionDescriptor(), list = new ActionList(), mesh = new ActionDescriptor(), desc = new ActionDescriptor(), i;
        for (i = 0; i < FACE_KEYS.length; i++) values.putDouble(s(FACE_KEYS[i]), FACE_KEYS[i] === "faceWidth" ? amount : 0);
        featureInfo.putObject(s("featureValues"), s("featureValues"), values); featureInfo.putObject(s("featureDisplacements"), s("featureDisplacements"), new ActionDescriptor()); list.putObject(s("faceInfo"), featureInfo);
        mesh.putInteger(s("faceDescriptorVersion"), 2); mesh.putInteger(s("faceMeshVersion"), 2); mesh.putList(s("faceInfoList"), list); desc.putObject(s("faceMesh"), s("faceMesh"), mesh); return desc;
    }
    function removeTemp(ctx, temporary) {
        // Compare document objects while they are still valid. Photoshop can
        // invalidate even object comparisons after a document has been closed.
        var i; for (i = ctx.temps.length - 1; i >= 0; i--) if (ctx.temps[i] === temporary) { ctx.temps.splice(i, 1); break; }
        try { temporary.close(SaveOptions.DONOTSAVECHANGES); }
        catch (closeError) { ctx.temps.push(temporary); throw closeError; }
    }
    function independentLayer(d, source, donor, ctx, before) {
        if (source === "target") { var copied = donor.duplicate(); copied.allLocked = false; copied.move(donor, ElementPlacement.PLACEBEFORE); return copied; }
        var temporary = null, l = null;
        try {
            temporary = d.duplicate("RT_liquify_snapshot_" + ctx.id, true); ctx.temps.push(temporary); app.activeDocument = temporary; invariant(temporary, before); fullCanvas(temporary.activeLayer, temporary);
            l = temporary.activeLayer.duplicate(d, ElementPlacement.PLACEATBEGINNING);
        } finally { try { if (temporary) removeTemp(ctx, temporary); } finally { app.activeDocument = d; } }
        if (!l) fail("Merged snapshot did not create an independent layer"); l.allLocked = false; return l;
    }
    function addMask(d, l, op) {
        var desc = layerDescriptor(d, l); if (flag(desc, "hasUserMask") || flag(desc, "hasVectorMask")) fail("New layer already has a mask; existing masks are never replaced");
        rgb(d); d.selection.deselect();
        if (op.mask === "roi") { var r = op.roi; d.selection.select([[r[0], r[1]], [r[2], r[1]], [r[2], r[3]], [r[0], r[3]]], SelectionType.REPLACE, op.feather === undefined ? 0 : op.feather, true); }
        else d.selection.selectAll();
        var select = new ActionDescriptor(), layerRef = new ActionReference(); layerRef.putIdentifier(c("Lyr "), l.id); select.putReference(c("null"), layerRef); select.putBoolean(c("MkVs"), false); executeAction(c("slct"), select, DialogModes.NO);
        var make = new ActionDescriptor(), maskRef = new ActionReference(); make.putClass(c("Nw  "), c("Chnl")); maskRef.putEnumerated(c("Chnl"), c("Chnl"), c("Msk ")); make.putReference(c("At  "), maskRef); make.putEnumerated(c("Usng"), c("UsrM"), c("RvlS")); executeAction(c("Mk  "), make, DialogModes.NO);
        // Photoshop 2020 uses the verified reveal-selection then fill-black route.
        // Direct hide-all mask creation is deliberately not used.
        if (op.mask === "black") {
            var channelSelect = new ActionDescriptor(), channelRef = new ActionReference(); channelRef.putEnumerated(c("Chnl"), c("Chnl"), c("Msk ")); channelSelect.putReference(c("null"), channelRef); executeAction(c("slct"), channelSelect, DialogModes.NO);
            var black = new SolidColor(); black.rgb.red = black.rgb.green = black.rgb.blue = 0; d.selection.selectAll(); d.selection.fill(black);
        }
        d.selection.deselect(); rgb(d);
    }
    function apply(d, op, ctx) {
        if (!ctx || !(ctx.temps instanceof Array) || !ctx.manifest) fail("RetouchRuntime context is required");
        var prepared = validateInput(d, op, ctx), before = info(d), donor = null, parent = null, l = null;
        if (layerHits(d, { name: op.name }).length) fail("New layer name must be unique: " + op.name);
        if (op.parent !== undefined) { parent = target(d, op.parent); if (parent.typename !== "LayerSet") fail("parent must be a group"); }
        if (prepared.source === "target") {
            donor = target(d, op.target); if (donor.typename !== "ArtLayer" || donor.kind !== LayerKind.NORMAL) fail("target must be a full-canvas pixel layer");
            var ld = layerDescriptor(d, donor); if (flag(ld, "hasUserMask") || flag(ld, "hasVectorMask") || ld.hasKey(s("layerEffects")) || donor.grouped || donor.opacity !== 100 || donor.fillOpacity !== 100 || donor.blendMode !== BlendMode.NORMAL) fail("target must be an unmasked, unclipped pixel layer at normal 100 percent without layer effects"); fullCanvas(donor, d);
        }
        var record = { version: VERSION, stageIndex: ctx.stageIndex === undefined ? null : ctx.stageIndex, type: op.type, name: op.name, source: prepared.source, parameters: prepared.parameters || null, mesh: prepared.mesh || null, opacity: op.opacity === undefined ? 100 : op.opacity, visible: op.visible === undefined ? true : op.visible, mask: op.mask === undefined ? null : op.mask, roi: op.roi === undefined ? null : op.roi.slice(0), feather: op.mask === "roi" ? (op.feather === undefined ? 0 : op.feather) : null, parentSelector: op.parent || null, snapshotDependencies: prepared.source === "mergedVisible" ? visibleDependencies(d) : null, opaqueBackground: prepared.opaqueBackground || null, targetReplacement: donor ? { donor: { id: donor.id, name: donor.name }, donorVisibilityBefore: donor.visible, donorParentId: donor.parent.typename === "LayerSet" ? donor.parent.id : null, donorHidden: false, comparison: "Hide the new layer and restore the donor's previous visibility to compare; the original donor pixels remain available." } : null, status: "prepared", commandAttempted: false, commandExecuted: false, pixelEffectUnverified: true, filterMs: null, layer: null };
        if (!ctx.manifest.nativeLiquify) ctx.manifest.nativeLiquify = []; ctx.manifest.nativeLiquify.push(record);
        var start = null;
        try {
            app.activeDocument = d; rgb(d); d.selection.deselect(); l = independentLayer(d, prepared.source, donor, ctx, before); l.name = op.name; fullCanvas(l, d);
            if (prepared.source === "mergedVisible") { if (l.parent.typename !== "Document" || d.layers[0].id !== l.id) l.move(d.layers[0], ElementPlacement.PLACEBEFORE); if (l.parent.typename !== "Document" || d.layers[0].id !== l.id) fail("Merged snapshot must be the top layer at the document root"); }
            else { if (parent) l.move(parent, ElementPlacement.INSIDE); donor.visible = false; record.targetReplacement.donorHidden = true; }
            l.opacity = 100; l.fillOpacity = 100; l.blendMode = BlendMode.NORMAL; l.visible = true; app.activeDocument = d; rgb(d); d.selection.deselect(); d.activeLayer = l;
            record.layer = { id: l.id, name: l.name, parentId: l.parent.typename === "LayerSet" ? l.parent.id : null }; var action = prepared.raw !== undefined ? new ActionDescriptor() : faceDescriptor(op.faceWidth); if (prepared.raw !== undefined) action.putData(c("LqMe"), prepared.raw);
            start = new Date().getTime(); record.commandAttempted = true; executeAction(c("LqFy"), action, DialogModes.NO); record.filterMs = new Date().getTime() - start; record.commandExecuted = true; record.status = "commandExecuted";
            invariant(d, before); fullCanvas(l, d); if (op.mask !== undefined) addMask(d, l, op); l.opacity = op.opacity === undefined ? 100 : op.opacity; l.visible = op.visible === undefined ? true : op.visible; return l;
        } catch (e) {
            if (start !== null && record.filterMs === null) record.filterMs = new Date().getTime() - start; record.status = "failed"; record.error = String(e.message);
            // The owning runtime rolls back a continuation or closes its new copy.
            throw e;
        } finally { app.activeDocument = d; d.selection.deselect(); rgb(d); }
    }
    return { version: VERSION, probe: probe, validateInput: validateInput, apply: apply };
}());
