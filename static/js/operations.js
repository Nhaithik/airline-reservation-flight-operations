let currentReservation=null;

const esc = escapeHtml; // api() and escapeHtml() come from app.js

async function loadReservations(){
  try{
    const rows=await api("/api/reservation-options");
    const sel=document.getElementById("reservationId");
    sel.innerHTML='<option value="">Select reservation</option>';
    rows.forEach(r=>{
      sel.insertAdjacentHTML("beforeend",
        `<option value="${r.reservation_id}">#${r.reservation_id} · ${esc(r.passenger_name)} · ${esc(r.flight_number)} · ${esc(r.seat_number)} · ${esc(r.reservation_status)}</option>`);
    });
  }catch(e){showToast(e.message,true);}
}

async function loadReservation(){
  const id=document.getElementById("reservationId").value;
  document.getElementById("seatMap").innerHTML="";
  if(!id){ currentReservation=null; document.getElementById("reservationSummary").textContent="Select a reservation to continue."; loadRefundPreview(); return; }
  try{
    currentReservation=await api(`/api/reservation/${id}`);
    document.getElementById("reservationSummary").innerHTML=`
      <div class="summary-grid">
        <div><span>Reservation</span><strong>#${currentReservation.reservation_id}</strong></div>
        <div><span>Passenger</span><strong>${esc(currentReservation.passenger_name)}</strong></div>
        <div><span>Flight</span><strong>${esc(currentReservation.flight_number)}</strong></div>
        <div><span>Route</span><strong>${esc(currentReservation.source)} → ${esc(currentReservation.destination)}</strong></div>
        <div><span>Seat</span><strong>${esc(currentReservation.seat_number)}</strong></div>
        <div><span>Status</span><strong>${esc(currentReservation.reservation_status)}</strong></div>
      </div>`;
    await loadSeatMap(currentReservation.flight_id);
    await loadRefundPreview();
  }catch(e){showToast(e.message,true);}
}

async function loadSeatMap(flightId){
  try{
    const data=await api(`/api/seat-map/${flightId}`);
    document.getElementById("seatInfo").textContent=
      `${data.flight.flight_number} · ${data.flight.available_seats} available seats in flight inventory`;
    const map=document.getElementById("seatMap");
    map.innerHTML="";
    data.seats.forEach(s=>{
      const b=document.createElement("button");
      b.type="button";
      b.className="seat "+(s.occupied?"occupied":"available");
      b.textContent=s.seat_number;
      b.disabled=s.occupied;
      if(s.seat_number===String(currentReservation?.seat_number||"").toUpperCase()) b.classList.add("selected");
      b.title=s.occupied?"Occupied":"Available";
      b.onclick=()=>changeSeat(s.seat_number);
      map.appendChild(b);
    });
  }catch(e){showToast(e.message,true);}
}

async function changeSeat(seat){
  if(!currentReservation) return showToast("Select a reservation first.",true);
  if(String(currentReservation.seat_number).toUpperCase()===seat) return showToast(`Reservation already has seat ${seat}.`,false);
  if(!confirm(`Move reservation #${currentReservation.reservation_id} to seat ${seat}?`)) return;
  try{
    const data=await api("/api/change-seat",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({reservation_id:currentReservation.reservation_id,seat_number:seat})});
    showToast(data.message);
    const keep=currentReservation.reservation_id;
    await loadReservations();
    document.getElementById("reservationId").value=keep;
    await loadReservation();
  }catch(e){showToast(e.message,true);}
}

async function loadRefundPreview(){
  const box=document.getElementById("refundPreview");
  if(!box||!currentReservation){ if(box) box.textContent=""; return; }
  try{
    const r=await api(`/api/refund-preview/${currentReservation.reservation_id}`);
    box.innerHTML=`Paid: <strong>₹${r.paid_amount.toFixed(2)}</strong> · Refund if cancelled now: <strong>${r.refund_percent}%</strong> = <strong>₹${r.refund_amount.toFixed(2)}</strong>`;
  }catch(e){ box.textContent=""; }
}

document.getElementById("reservationId").addEventListener("change",loadReservation);

document.getElementById("paymentForm").addEventListener("submit",async e=>{
  e.preventDefault();
  if(!currentReservation) return showToast("Select a reservation first.",true);
  try{
    const data=await api("/api/payment",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({
      reservation_id:currentReservation.reservation_id,
      amount:document.getElementById("paymentAmount").value,
      method:document.getElementById("paymentMethod").value,
      reference:document.getElementById("paymentReference").value.trim()
    })});
    document.getElementById("ticketResult").textContent="Payment successful. You can now issue the ticket.";
    showToast(`Payment successful. Reservation #${data.reservation_id} confirmed.`);
    await loadReservations(); document.getElementById("reservationId").value=currentReservation.reservation_id; await loadReservation();
  }catch(e){showToast(e.message,true);}
});

document.getElementById("ticketBtn").addEventListener("click",async()=>{
  if(!currentReservation) return showToast("Select a reservation first.",true);
  try{
    const data=await api("/api/ticket",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({reservation_id:currentReservation.reservation_id})});
    document.getElementById("ticketResult").innerHTML=`<strong>${esc(data.ticket_number)}</strong> — ${esc(data.message)}`;
    showToast("Ticket issued successfully.");
  }catch(e){showToast(e.message,true);}
});

document.getElementById("checkinForm").addEventListener("submit",async e=>{
  e.preventDefault();
  if(!currentReservation) return showToast("Select a reservation first.",true);
  try{
    const data=await api("/api/checkin",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({
      reservation_id:currentReservation.reservation_id,
      gate:document.getElementById("gateNumber").value.trim()
    })});
    document.getElementById("checkinResult").innerHTML=`Boarding Pass <strong>${esc(data.boarding_pass_number)}</strong> · Gate <strong>${esc(data.gate_number)}</strong>`;
    showToast("Check-in successful.");
  }catch(e){showToast(e.message,true);}
});

document.getElementById("baggageForm").addEventListener("submit",async e=>{
  e.preventDefault();
  if(!currentReservation) return showToast("Select a reservation first.",true);
  try{
    const data=await api("/api/baggage",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({
      reservation_id:currentReservation.reservation_id,
      weight:document.getElementById("baggageWeight").value
    })});
    document.getElementById("baggageResult").innerHTML=`Baggage ID <strong>#${esc(data.baggage_id)}</strong> recorded.`;
    showToast("Baggage recorded.");
  }catch(e){showToast(e.message,true);}
});

document.getElementById("cancelForm").addEventListener("submit",async e=>{
  e.preventDefault();
  if(!currentReservation) return showToast("Select a reservation first.",true);
  if(!confirm("Cancel this reservation? This will release one flight seat.")) return;
  try{
    const data=await api("/api/cancel",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({
      reservation_id:currentReservation.reservation_id,
      reason:document.getElementById("cancelReason").value.trim()
    })});
    document.getElementById("cancelResult").innerHTML=`Cancelled successfully. Paid ₹${Number(data.paid_amount).toFixed(2)} · Refund ${data.refund_percent}% = <strong>₹${Number(data.refund_amount).toFixed(2)}</strong>`;
    showToast("Reservation cancelled.");
    await loadReservations();
    document.getElementById("reservationId").value="";
    await loadReservation();
  }catch(e){showToast(e.message,true);}
});

document.addEventListener("DOMContentLoaded",loadReservations);
