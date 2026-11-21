# Compara el orden por población con el menor tiempo de conducción.
# Uso: Rscript notebooks/cruz_verde.R <ruta-de-python> [top7|comparacion]
args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 1L || length(args) > 2L) stop("Indica la ruta de Python y, opcionalmente, el escenario.")
escenario <- if (length(args) == 2L) match.arg(args[2L], c("top7", "comparacion")) else "top7"
script_arg <- grep("^--file=", commandArgs(), value = TRUE)
carpeta <- dirname(normalizePath(sub("^--file=", "", script_arg)))
matrices <- tempfile(fileext = ".csv")
estado <- system2(args[1], shQuote(c(file.path(carpeta, "cruz_verde_matrices.py"), matrices, escenario)))
if (estado != 0L) stop("Falló la preparación de tiempos sobre la red vial.")
datos <- read.csv(matrices, encoding = "UTF-8")
unlink(matrices)

permutar <- function(x) {
  if (length(x) == 1L) return(matrix(x, nrow = 1L))
  do.call(rbind, lapply(x, function(primera) cbind(primera, permutar(x[x != primera]))))
}

for (municipio in unique(datos$municipio)) {
  caso <- datos[datos$municipio == municipio, ]
  cat("\n", caso$rango[1L], ". ", municipio, sep = "")
  if (!is.na(caso$acceso_hospital[1L])) {
    cat(sprintf(" | Acceso al hospital: %.2f min", caso$acceso_hospital[1L]))
  }
  cat("\n")
  if (caso$estado[1L] != "OK") {
    cat(caso$estado[1L], "\n")
    next
  }
  puntos <- caso[caso$origen == caso$destino, ]
  n <- nrow(puntos)
  tiempos <- matrix(NA_real_, n, n, dimnames = list(puntos$localidad, puntos$localidad))
  tiempos[cbind(caso$origen, caso$destino)] <- caso$minutos
  stopifnot(all(is.finite(tiempos)), all(diag(tiempos) == 0))
  rutas <- cbind(1L, permutar(seq.int(2L, n)), 1L)
  costo <- function(ruta) sum(tiempos[cbind(head(ruta, -1L), tail(ruta, -1L))])
  totales <- apply(rutas, 1L, costo)
  referencia <- c(seq_len(n), 1L)
  mejor <- rutas[which(totales <= min(totales) + 1e-9)[1L], ]
  inicial <- costo(referencia)
  optimo <- costo(mejor)
  stopifnot(optimo <= inicial + 1e-9)
  detalle <- function(ruta) paste(puntos$localidad[ruta], collapse = " > ")
  cat(sprintf("Referencia: %s | %.3f min\n", detalle(referencia), inicial))
  cat(sprintf("Optimizada: %s | %.3f min\n", detalle(mejor), optimo))
  cat(sprintf("Ahorro: %.3f min (%.2f%%)\n", inicial - optimo, 100 * (inicial - optimo) / inicial))
  print(puntos[c("localidad", "poblacion", "ajuste_m")], row.names = FALSE)
  print(round(tiempos, 2))
}
