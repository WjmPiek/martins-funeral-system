(function () {
  const ctx = window.HEATMAP_CONTEXT || {};
  const state = { records: [], filtered: [], mode: 'density', map: null, heatLayer: null, markers: [], geocoder: null };
  const $ = (id) => document.getElementById(id);

  function esc(v) { return String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
  function numeric(v) { const n = Number(v); return Number.isFinite(n) ? n : null; }
  function hasPoint(r) { return numeric(r.latitude) !== null && numeric(r.longitude) !== null; }
  function fullAddress(r) { return r.fullAddress || [r.address, r.city, r.province, r.country || 'South Africa'].filter(Boolean).join(', '); }

  function filteredRecords() {
    const town = ($('heatTownFilter')?.value || '').trim().toLowerCase();
    const province = $('heatProvinceFilter')?.value || '';
    state.filtered = state.records.filter(r => {
      return (!town || String(r.city || '').toLowerCase().includes(town) || String(fullAddress(r)).toLowerCase().includes(town)) &&
             (!province || r.province === province);
    });
    return state.filtered;
  }

  function updateStats() {
    const records = state.filtered || [];
    const mapped = records.filter(hasPoint).length;
    if ($('heatTotal')) $('heatTotal').textContent = records.length;
    if ($('heatMapped')) $('heatMapped').textContent = mapped;
    if ($('heatUnmapped')) $('heatUnmapped').textContent = records.length - mapped;
    if ($('heatModeLabel')) $('heatModeLabel').textContent = state.mode.charAt(0).toUpperCase() + state.mode.slice(1);
  }

  function popup(record) {
    const mapsLink = hasPoint(record) ? `<a href="https://www.google.com/maps?q=${record.latitude},${record.longitude}" target="_blank" rel="noopener">Open in Google Maps</a>` : '';
    return `<div class="heatmap-popup">
      <strong>${esc(record.deceasedName)} ${esc(record.deceasedSurname)}</strong>
      <div><b>MF File:</b> ${esc(record.mfFile || '-')}</div>
      <div><b>Franchise:</b> ${esc(record.franchiseName || '-')}</div>
      <div><b>Town:</b> ${esc(record.city || '-')}</div>
      <div><b>Province:</b> ${esc(record.province || '-')}</div>
      <div><b>Address:</b> ${esc(fullAddress(record) || '-')}</div>
      <div><b>Contact:</b> ${esc(record.contactNumber || '-')}</div>
      ${mapsLink}
    </div>`;
  }

  function clearMap() {
    state.markers.forEach(m => m.setMap(null));
    state.markers = [];
    if (state.heatLayer) state.heatLayer.setMap(null);
    state.heatLayer = null;
  }

  function renderMap(fit) {
    if (!state.map || !window.google) return;
    clearMap();
    const radius = Number($('heatRadius')?.value || 30);
    const mapped = (state.filtered || []).filter(hasPoint);
    const bounds = new google.maps.LatLngBounds();
    const heatPoints = [];

    mapped.forEach(record => {
      const pos = { lat: Number(record.latitude), lng: Number(record.longitude) };
      bounds.extend(pos);
      heatPoints.push({ location: new google.maps.LatLng(pos.lat, pos.lng), weight: Number(record.weight || 1) });
      if (state.mode === 'pins' || state.mode === 'both' || state.mode === 'clusters') {
        const marker = new google.maps.Marker({ position: pos, map: state.map, title: record.mfFile || record.city || 'Heat map point' });
        const infowindow = new google.maps.InfoWindow({ content: popup(record) });
        marker.addListener('click', () => infowindow.open({ anchor: marker, map: state.map }));
        state.markers.push(marker);
      }
    });

    if ((state.mode === 'density' || state.mode === 'both') && heatPoints.length) {
      state.heatLayer = new google.maps.visualization.HeatmapLayer({ data: heatPoints, radius });
      state.heatLayer.setMap(state.map);
    }

    if (fit && mapped.length) {
      if (mapped.length === 1) state.map.setCenter(bounds.getCenter());
      state.map.fitBounds(bounds);
    }
  }

  function renderTable() {
    const body = $('heatRows');
    if (!body) return;
    const records = state.filtered || [];
    const colspan = ctx.canModify ? 8 : 7;
    if (!records.length) {
      body.innerHTML = `<tr><td colspan="${colspan}">No heat map records found.</td></tr>`;
      return;
    }
    body.innerHTML = records.slice(0, 500).map(record => `
      <tr class="${hasPoint(record) ? '' : 'warning-row'}">
        <td>${esc(record.mfFile)}</td>
        <td>${esc(record.franchiseName)}</td>
        <td>${esc(record.deceasedName)} ${esc(record.deceasedSurname)}</td>
        <td>${esc(record.city)}</td>
        <td>${esc(record.province)}</td>
        <td>${esc(fullAddress(record))}</td>
        <td>${esc(record.contactNumber)}</td>
        ${ctx.canModify ? `<td><button type="button" class="btn small danger-btn" data-delete="${record.id}">Delete</button></td>` : ''}
      </tr>`).join('');
  }

  function applyFilters(fit) {
    filteredRecords();
    updateStats();
    renderTable();
    renderMap(fit);
  }

  async function loadData(fit) {
    const franchiseId = $('heatFranchiseFilter')?.value || '';
    const url = new URL(ctx.dataUrl, window.location.origin);
    if (franchiseId) url.searchParams.set('franchise_id', franchiseId);
    const res = await fetch(url.toString());
    const data = await res.json();
    state.records = data.records || [];
    applyFilters(fit);
  }

  async function geocodeMissing() {
    if (!ctx.canModify || !state.geocoder) return;
    const missing = (state.filtered || []).filter(r => !hasPoint(r) && fullAddress(r)).slice(0, 50);
    if (!missing.length) { alert('No missing coordinates in the current view.'); return; }
    if (!confirm(`Geocode and save up to ${missing.length} missing address(es)?`)) return;
    for (const record of missing) {
      await new Promise(resolve => {
        state.geocoder.geocode({ address: fullAddress(record), componentRestrictions: { country: 'ZA' } }, async (results, status) => {
          if (status === 'OK' && results && results[0]) {
            const loc = results[0].geometry.location;
            record.latitude = loc.lat();
            record.longitude = loc.lng();
            try {
              await fetch(ctx.saveUrl, { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(record) });
            } catch (e) { console.warn(e); }
          }
          setTimeout(resolve, 250);
        });
      });
    }
    await loadData(true);
  }

  async function deleteRecord(id) {
    if (!ctx.canModify || !confirm('Delete this heat map record?')) return;
    const res = await fetch(`/heat-map/record/${encodeURIComponent(id)}/delete`, { method: 'POST' });
    if (!res.ok) { alert('Could not delete record.'); return; }
    await loadData(false);
  }

  window.initMartinsHeatMap = function () {
    state.map = new google.maps.Map($('heatMap'), { center: { lat: -28.4793, lng: 24.6727 }, zoom: 5, mapTypeId: 'roadmap' });
    state.geocoder = new google.maps.Geocoder();
    loadData(true);
  };

  document.addEventListener('DOMContentLoaded', function () {
    ['heatTownFilter', 'heatProvinceFilter', 'heatRadius'].forEach(id => $(id)?.addEventListener('input', () => applyFilters(false)));
    $('heatFranchiseFilter')?.addEventListener('change', () => loadData(true));
    $('heatFitBoundsBtn')?.addEventListener('click', () => renderMap(true));
    $('heatGeocodeBtn')?.addEventListener('click', geocodeMissing);
    document.querySelectorAll('[data-heat-mode]').forEach(btn => btn.addEventListener('click', function () {
      state.mode = this.dataset.heatMode;
      document.querySelectorAll('[data-heat-mode]').forEach(b => b.classList.add('secondary'));
      this.classList.remove('secondary');
      applyFilters(false);
    }));
    $('heatRows')?.addEventListener('click', function (event) {
      const btn = event.target.closest('[data-delete]');
      if (btn) deleteRecord(btn.dataset.delete);
    });
  });
})();
