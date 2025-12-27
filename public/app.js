document.getElementById('chat-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const input = document.getElementById('user-input');
  const message = input.value.trim();
  if (!message) return;
  displayMessage('user', message);
  input.value = '';
  // For demo, echo back after 1s
  setTimeout(() => {
    displayMessage('assistant', 'Echo: ' + message);
  }, 1000);
});

function displayMessage(sender, text) {
  const msgDiv = document.createElement('div');
  msgDiv.className = 'message ' + sender;
  msgDiv.textContent = text;
  document.getElementById('messages').appendChild(msgDiv);
}