const socket = io();
const approveBtn = document.getElementById('approve-btn');
let currentRisks = [];
let currentDraft = [];

socket.on('update_data', (data) => {
    console.log('Data Update:', data);
    document.getElementById('rainfall').textContent = `${data.env.rainfall}mm`;
    document.getElementById('flood_zone').textContent = data.env.flood_zone;
    document.getElementById('road_status').textContent = data.env.road_status;
    document.getElementById('draft_plan').textContent = data.draft_plan.length ? data.draft_plan[0] : "None";
    document.getElementById('plan').textContent = data.env.approved ? (data.env.plan.length ? data.env.plan[0] : "None") : "Not Approved";
    document.getElementById('risks').textContent = data.risks.length ? `Risks: ${data.risks.join(', ')}` : 'No risks yet.';
    currentRisks = data.risks;
    currentDraft = data.draft_plan;
    approveBtn.disabled = !data.draft_plan.length || !data.draft_plan[0] || data.env.approved;
    approveBtn.textContent = data.env.approved && data.draft_plan[0] !== data.env.plan[0] ? "Approve Updated Plan" : "Approve Plan";
});

socket.on('update_plan', (data) => {
    console.log('Plan Update:', data);
    document.getElementById('plan').textContent = data.plan.length ? data.plan[0] : "None";
});

approveBtn.onclick = () => {
    console.log('Approve clicked', { risks: currentRisks, draft_plan: currentDraft });
    socket.emit('approve_plan', { risks: currentRisks, draft_plan: currentDraft });
};