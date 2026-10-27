#define NOMINMAX
#include <windows.h>
#include <shlobj.h>
#include <shellapi.h>
#include <bcrypt.h>
#include <filesystem>
#include <fstream>
#include <array>
#include <string>
#include <stdexcept>
#include <vector>
#include <cstdlib>
#include "LzmaDec.h"
#include "package_files.h"

namespace fs = std::filesystem;

std::string Digest(const fs::path &path) {
	BCRYPT_ALG_HANDLE algorithm = nullptr;
	BCRYPT_HASH_HANDLE hash = nullptr;
	if (BCryptOpenAlgorithmProvider(&algorithm, BCRYPT_SHA256_ALGORITHM, nullptr, 0) < 0) {
		throw std::runtime_error("sha256 provider");
	}
	struct Cleanup {
		BCRYPT_ALG_HANDLE &algorithm;
		BCRYPT_HASH_HANDLE &hash;
		~Cleanup() {
			if (hash) BCryptDestroyHash(hash);
			if (algorithm) BCryptCloseAlgorithmProvider(algorithm, 0);
		}
	} cleanup{ algorithm, hash };
	if (BCryptCreateHash(algorithm, &hash, nullptr, 0, nullptr, 0, 0) < 0) {
		throw std::runtime_error("sha256 init");
	}
	auto input = std::ifstream(path, std::ios::binary);
	if (!input) return {};
	auto buffer = std::array<char, 65536>();
	while (input) {
		input.read(buffer.data(), buffer.size());
		if (BCryptHashData(hash, reinterpret_cast<PUCHAR>(buffer.data()),
			static_cast<ULONG>(input.gcount()), 0) < 0) {
			throw std::runtime_error("sha256 update");
		}
	}
	if (!input.eof()) throw std::runtime_error("read failed");
	auto bytes = std::array<unsigned char, 32>();
	if (BCryptFinishHash(hash, bytes.data(), static_cast<ULONG>(bytes.size()), 0) < 0) {
		throw std::runtime_error("sha256 finish");
	}
	const auto alphabet = "0123456789abcdef";
	auto result = std::string();
	for (const auto byte : bytes) {
		result += alphabet[byte >> 4];
		result += alphabet[byte & 15];
	}
	return result;
}

void *Allocate(ISzAllocPtr, size_t size) {
	return std::malloc(size);
}

void Free(ISzAllocPtr, void *address) {
	std::free(address);
}

void Extract(const PackageFile &file, const fs::path &destination) {
	const auto module = GetModuleHandleW(nullptr);
	const auto resource = FindResourceW(module, MAKEINTRESOURCEW(file.resource), RT_RCDATA);
	const auto size = resource ? SizeofResource(module, resource) : 0;
	const auto loaded = resource ? LoadResource(module, resource) : nullptr;
	const auto bytes = loaded ? static_cast<const Byte*>(LockResource(loaded)) : nullptr;
	if (!bytes || size <= 13 || !file.size || file.size > 1024ULL * 1024 * 1024) {
		throw std::runtime_error("embedded package missing");
	}
	auto output = std::vector<Byte>(file.size);
	auto outputSize = SizeT(output.size());
	auto inputSize = SizeT(size - 13);
	auto status = ELzmaStatus();
	const auto allocator = ISzAlloc{ Allocate, Free };
	const auto result = LzmaDecode(output.data(), &outputSize, bytes + 13, &inputSize,
		bytes, LZMA_PROPS_SIZE, LZMA_FINISH_END, &status, &allocator);
	if (result != SZ_OK || outputSize != output.size() || inputSize != size - 13
		|| status != LZMA_STATUS_FINISHED_WITH_MARK) {
		throw std::runtime_error("embedded package damaged");
	}
	auto stream = std::ofstream(destination, std::ios::binary | std::ios::trunc);
	stream.write(reinterpret_cast<const char*>(output.data()), output.size());
	stream.close();
	if (!stream) throw std::runtime_error("write failed");
}

std::string Updated(const fs::path &path) {
	auto input = std::ifstream(fs::path(path.wstring() + L".updated"), std::ios::binary);
	auto result = std::string(64, '\0');
	if (!input.read(result.data(), result.size())) return {};
	return result;
}

fs::path DefaultRoot() {
	PWSTR path = nullptr;
	if (FAILED(SHGetKnownFolderPath(FOLDERID_LocalAppData, 0, nullptr, &path))) {
		throw std::runtime_error("local app data");
	}
	const auto result = fs::path(path) / L"mad-single";
	CoTaskMemFree(path);
	return result;
}

fs::path Prepare(const fs::path &root) {
	const auto target = root / L"app" / kBuild;
	for (const auto &file : kFiles) {
		const auto destination = target / file.path;
		if (fs::is_regular_file(destination)) {
			const auto current = Digest(destination);
			if (current == file.sha256 || (!current.empty() && current == Updated(destination))) {
				continue;
			}
		}
		fs::create_directories(destination.parent_path());
		const auto temporary = fs::path(destination.wstring() + L".tmp-" + std::to_wstring(GetCurrentProcessId()));
		try {
			Extract(file, temporary);
			if (Digest(temporary) != file.sha256) throw std::runtime_error("package integrity");
			if (!MoveFileExW(temporary.c_str(), destination.c_str(),
				MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH)) {
				throw std::runtime_error("replace failed");
			}
		} catch (...) {
			auto error = std::error_code();
			fs::remove(temporary, error);
			throw;
		}
	}
	fs::create_directories(root / L"profile");
	return target / L"mad.exe";
}

int WINAPI wWinMain(HINSTANCE, HINSTANCE, PWSTR, int) {
	auto count = 0;
	const auto arguments = CommandLineToArgvW(GetCommandLineW(), &count);
	if (!arguments) return 2;
	const auto testing = count == 3 && std::wstring(arguments[1]) == L"--prepare-only";
	if (count != 1 && !testing) {
		LocalFree(arguments);
		return 2;
	}
	try {
		const auto root = testing ? fs::absolute(arguments[2]) : DefaultRoot();
		LocalFree(arguments);
		const auto mutexName = std::wstring(L"Local\\mad-single-") + kBuild;
		const auto mutex = CreateMutexW(nullptr, FALSE, mutexName.c_str());
		if (!mutex) throw std::runtime_error("mutex");
		struct Lock {
			HANDLE handle;
			~Lock() { ReleaseMutex(handle); CloseHandle(handle); }
		} lock{ mutex };
		const auto wait = WaitForSingleObject(mutex, 60000);
		if (wait != WAIT_OBJECT_0 && wait != WAIT_ABANDONED) throw std::runtime_error("busy");
		const auto executable = Prepare(root);
		if (testing) return 0;
		const auto profile = root / L"profile";
		auto command = L"\"" + executable.wstring() + L"\" -workdir \"" + profile.wstring() + L"\"";
		auto startup = STARTUPINFOW();
		startup.cb = sizeof(startup);
		auto process = PROCESS_INFORMATION();
		if (!CreateProcessW(executable.c_str(), command.data(), nullptr, nullptr, FALSE,
			0, nullptr, profile.c_str(), &startup, &process)) {
			throw std::runtime_error("launch failed");
		}
		CloseHandle(process.hThread);
		CloseHandle(process.hProcess);
		return 0;
	} catch (...) {
		if (!testing) {
			MessageBoxW(nullptr,
				L"не удалось подготовить mad. проверь свободное место и доступ к папке пользователя, затем запусти файл снова.",
				L"mad", MB_OK | MB_ICONERROR);
		}
		return 1;
	}
}
