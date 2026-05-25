from dataclasses import dataclass, field


@dataclass
class Animal:
    name: str
    species: str
    age: int
    color: str = field(default="unknown")

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "species": self.species,
            "age": self.age,
            "color": self.color,
        }

@dataclass
class Dog(Animal):
    breed: str = field(default="unknown")
    names: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        base_dict = super().to_dict()
        base_dict["breed"] = self.breed
        return base_dict


def main():
    dog1 = Dog(name="Buddy", species="Canis lupus familiaris", age=5, color="brown", breed="Labrador")
    dog2 = Dog(name="Buddy", species="Canis lupus familiaris", age=5, color="brown", breed="Labrador")

    print(dog1.to_dict())


if __name__ == "__main__":
    main()  