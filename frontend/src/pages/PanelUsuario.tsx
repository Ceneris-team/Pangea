import { Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import Sidebar from "../components/layout/Sidebar";
import Topbar from "../components/layout/Topbar";

export default function PanelUsuario() {
	const { nombreCompleto, rol, logout } = useAuth();

	return (
		<div className="font-sans">
			<div className="flex h-screen bg-transparent transition-colors duration-300 overflow-hidden">
				<Sidebar onLogout={logout} activo="panel" rol={rol} />

				<div className="flex-1 flex flex-col overflow-hidden">
					<div className="flex justify-end p-4 md:p-6 pb-0">
					  <Topbar
						nombreCompleto={nombreCompleto}
						rol={rol}
					  />
					</div>

					<main className="flex-1 overflow-y-auto p-6 md:p-8">
						<header className="mb-6">
							<h1 className="text-2xl font-bold text-gray-900 dark:text-white">
								Hola, {nombreCompleto ?? "Cliente Final"}
							</h1>
							<p className="text-sm text-gray-600 dark:text-gray-300">
								Panel de Cliente Final - Pangea 4.0.
							</p>
						</header>

						<div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-2 gap-4">
							<Link
								to="/ubicaciones"
								className="bg-white/70 dark:bg-white/[0.04] backdrop-blur-md rounded-2xl shadow-sm border border-black/10 dark:border-white/10 p-6 hover:border-[#ccff00] transition-colors"
							>
								<div className="w-10 h-10 rounded-lg bg-[#ccff00]/20 flex items-center justify-center mb-3">
									<svg className="w-5 h-5 text-[#5a7000] dark:text-[#ccff00]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
										<path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17.657 16.657L13.414 20.9a2 2 0 01-2.828 0l-4.243-4.243a8 8 0 1111.314 0z" />
										<path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
									</svg>
								</div>
								<h2 className="font-semibold text-gray-900 dark:text-white">Ubicaciones</h2>
								<p className="text-sm text-gray-600 dark:text-gray-300">Consulta las sedes y estaciones asociadas a tu cuenta.</p>
							</Link>

							<Link
								to="/mi-perfil"
								className="bg-white/70 dark:bg-white/[0.04] backdrop-blur-md rounded-2xl shadow-sm border border-black/10 dark:border-white/10 p-6 hover:border-[#ccff00] transition-colors"
							>
								<div className="w-10 h-10 rounded-lg bg-[#ccff00]/20 flex items-center justify-center mb-3">
									<svg className="w-5 h-5 text-[#5a7000] dark:text-[#ccff00]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
										<path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5.121 17.804A9 9 0 1118.9 17.9" />
										<path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
									</svg>
								</div>
								<h2 className="font-semibold text-gray-900 dark:text-white">Mi perfil</h2>
								<p className="text-sm text-gray-600 dark:text-gray-300">Revisa y actualiza tus datos personales.</p>
							</Link>
						</div>
					</main>
				</div>
			</div>
		</div>
	);
}
