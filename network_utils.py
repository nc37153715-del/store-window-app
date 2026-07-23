"""로컬 네트워크(모바일) 접속용 IP 조회."""

from __future__ import annotations

import socket


def is_private_ip(ip: str) -> bool:
    parts = ip.split(".")
    if len(parts) != 4:
        return False
    try:
        octets = [int(part) for part in parts]
    except ValueError:
        return False
    if octets[0] == 10:
        return True
    if octets[0] == 192 and octets[1] == 168:
        return True
    if octets[0] == 172 and 16 <= octets[1] <= 31:
        return True
    return False


def _ip_sort_key(ip: str) -> tuple[int, str]:
    if ip.startswith("192.168."):
        return (0, ip)
    if ip.startswith("10."):
        return (1, ip)
    if ip.startswith("172."):
        return (2, ip)
    return (3, ip)


def get_all_local_ips() -> list[str]:
    """PC에서 핸드폰 접속에 쓸 IPv4 주소 목록."""
    found: set[str] = set()

    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if ip.startswith("127."):
                continue
            found.add(ip)
    except OSError:
        pass

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            found.add(sock.getsockname()[0])
    except OSError:
        pass

    private_ips = sorted((ip for ip in found if is_private_ip(ip)), key=_ip_sort_key)
    if private_ips:
        return private_ips

    return sorted(found, key=_ip_sort_key)


def get_local_ip() -> str | None:
    ips = get_all_local_ips()
    return ips[0] if ips else None


def get_mobile_access_urls(port: int = 8501) -> list[str]:
    return [f"http://{ip}:{port}" for ip in get_all_local_ips()]


def get_mobile_access_url(port: int = 8501) -> str | None:
    urls = get_mobile_access_urls(port)
    return urls[0] if urls else None


def get_test_access_urls(port: int = 8501) -> dict[str, str | list[str]]:
    network_urls = get_mobile_access_urls(port)
    return {
        "pc": f"http://localhost:{port}",
        "network": network_urls[0] if network_urls else f"http://localhost:{port}",
        "network_all": network_urls,
    }


def write_test_access_file(port: int = 8501, filename: str = "테스트_접속주소.txt") -> dict[str, str | list[str]]:
    urls = get_test_access_urls(port)
    network_urls = urls["network_all"]
    network_url = str(urls["network"])

    lines = [
        "Visual Check Guide — 핸드폰 접속 주소",
        "",
        f"PC(본인): {urls['pc']}",
        "",
        ">>> 핸드폰 브라우저에 아래 주소 입력 <<<",
    ]
    if network_urls:
        for index, url in enumerate(network_urls, start=1):
            lines.append(f"  {index}. {url}")
    else:
        lines.append("  (IP 없음 — ipconfig 로 IPv4 확인)")

    lines.extend(
        [
            "",
            "※ x.x 같은 예시가 아니라, 위에 적힌 숫자 그대로 입력",
            "※ 핸드폰: Wi-Fi ON / 모바일데이터 OFF",
            "※ PC에서 실행.bat 이 켜져 있어야 함",
            "※ 안 되면 방화벽_허용.bat (관리자) 실행",
        ]
    )

    with open(filename, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
        handle.write(f"\nOPEN_URL={network_url}\n")
        for index, url in enumerate(network_urls, start=1):
            handle.write(f"OPEN_URL_{index}={url}\n")
    return urls


def is_port_listening(port: int = 8501, host: str = "0.0.0.0") -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1.0)
            sock.bind((host, port))
    except OSError as exc:
        if getattr(exc, "winerror", None) == 10048 or exc.errno in (98, 10048):
            return True
        return False
    return False


def print_connection_diagnostics(port: int = 8501) -> None:
    print("=== Visual Check Guide 접속 진단 ===")
    print()
    print(f"[1] 포트 {port} 서버")
    if is_port_listening(port):
        print("    OK - 앱이 실행 중입니다")
    else:
        print("    X  - 앱이 꺼져 있습니다 -> 실행.bat 을 먼저 실행하세요")
    print()
    print("[2] 핸드폰에 입력할 주소 (아래 그대로 복사)")
    urls = get_mobile_access_urls(port)
    if urls:
        for index, url in enumerate(urls, start=1):
            marker = "  >>> " if index == 1 else "      "
            print(f"{marker}{index}. {url}")
    else:
        print("    X  - IP를 찾지 못했습니다 -> ipconfig 로 IPv4 확인")
    print()
    print("[3] 핸드폰 설정")
    print("    - Wi-Fi 켜기 / 모바일데이터(LTE) 끄기")
    print("    - 192.168.x.x 는 예시일 뿐, 위 [2]의 실제 주소 사용")
    print("    - PC 검은 창(실행.bat)을 닫지 마세요")
    print()
    print("[4] 여전히 안 되면")
    print("    - 방화벽_허용.bat -> 관리자 권한 실행")
    print("    - PC/폰이 서로 다른 Wi-Fi면 PC 핫스팟으로 연결")


if __name__ == "__main__":
    print_connection_diagnostics()
