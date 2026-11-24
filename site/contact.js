const address = document.getElementById('email-address');
const copyButton = document.getElementById('copy-email');
const emailStatus = document.getElementById('email-status');

copyButton.hidden = false;
copyButton.addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText(address.textContent.trim());
    emailStatus.textContent = '이메일 주소를 복사했습니다.';
  } catch {
    const range = document.createRange();
    range.selectNodeContents(address);
    const selection = window.getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
    emailStatus.textContent = '이메일 주소를 선택했습니다. 복사 메뉴로 복사해 주세요.';
  }
});
