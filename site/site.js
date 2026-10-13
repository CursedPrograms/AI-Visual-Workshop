// AI Visual Workshop - GitHub Pages site.
// "Run link.bf" runs the repo's link.bf (shown in the footer) with a small Brainfuck
// interpreter and turns what it prints into a link.
(function () {
  function runBrainfuck(code) {
    var tape = new Uint8Array(30000), p = 0, out = "", jump = {}, stack = [];
    for (var i = 0; i < code.length; i++) {
      if (code[i] === "[") stack.push(i);
      else if (code[i] === "]") { var j = stack.pop(); jump[i] = j; jump[j] = i; }
    }
    for (var pc = 0, steps = 0; pc < code.length && steps < 1e6; pc++, steps++) {
      switch (code[pc]) {
        case ">": p++; break;
        case "<": p--; break;
        case "+": tape[p]++; break;
        case "-": tape[p]--; break;
        case ".": out += String.fromCharCode(tape[p]); break;
        case "[": if (!tape[p]) pc = jump[pc]; break;
        case "]": if (tape[p]) pc = jump[pc]; break;
      }
    }
    return out;
  }

  var run = document.getElementById("bfRun");
  if (!run) return;
  run.addEventListener("click", function () {
    var printed = runBrainfuck(document.getElementById("bfCode").textContent);
    var out = document.getElementById("bfOut");
    out.textContent = printed;
    out.href = "https://" + printed + "/";
    out.hidden = false;
    run.textContent = "link.bf prints:";
    run.disabled = true;
  });
})();
