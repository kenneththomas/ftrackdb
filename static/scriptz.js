// Get the button element
var btnChangeColor = document.getElementById("btnChangeColor");

// Add click event listener to the button
btnChangeColor.addEventListener("click", function() {
  // Get the body element
  var body = document.body;

  // Toggle the 'bari-mode' class on the body element
  body.classList.toggle("bari-mode");
});

document.addEventListener("DOMContentLoaded", function() {
  setTimeout(function() {
    document.querySelector(".index-container").style.opacity = 1;
  }, 100); 
});