// pytoy — documentation (PDF edition)
//
// This is the Typst source for the PDF manual — the project's primary
// documentation. Build with ./build.sh (or `typst compile main.typ
// pytoy.pdf`).

#set document(title: "pytoy — A Python toolbox for the Toy CPU", author: "Manfred Scheucher")
#set page(paper: "a4", numbering: "1", margin: (x: 2.5cm, y: 2.5cm))
#set text(font: "New Computer Modern", size: 10.5pt, lang: "en")
#set par(justify: true, leading: 0.65em)
#set heading(numbering: "1.1")

// Monospace blocks a touch smaller, with a light background.
#show raw.where(block: true): it => block(
  fill: luma(245), inset: 8pt, radius: 3pt, width: 100%, it,
)

// Title page
#align(center + horizon)[
  #text(size: 26pt, weight: "bold")[pytoy]
  #v(0.4em)
  #text(size: 14pt)[A Python toolbox for the Toy CPU]
  #v(2em)
  #text(size: 11pt)[A Python assembler, simulator, and GUI debugger \
  for Jim Hall's minimal 8-bit educational processor]
  #v(4em)
  #text(size: 10pt, fill: luma(90))[Manfred Scheucher]
]

#pagebreak()

#outline(depth: 2, indent: auto)
#pagebreak()

#include "chapters/01-concepts.typ"
#pagebreak()
#include "chapters/02-instruction-set.typ"
#pagebreak()
#include "chapters/03-assembly.typ"
#pagebreak()
#include "chapters/07-writing-programs.typ"
#pagebreak()
#include "chapters/04-usage.typ"
#pagebreak()
#include "chapters/05-compiler.typ"
#pagebreak()
#include "chapters/08-stack-and-recursion.typ"
#pagebreak()
#include "chapters/06-toycpu.typ"
